from __future__ import annotations

import threading
import uuid

from .analysis import VERSION, REPRESENTATIONS, analyze, digest, prepare_models


class ExplorationBusy(RuntimeError):
    pass


class ExplorationService:
    """One active analysis per service; persistent results, cooperative cancel."""
    def __init__(self, store):
        self.store = store
        self._lock = threading.Lock()
        self._active = {}
        self._slots = threading.BoundedSemaphore(1)

    def start(self, experiment_id, representation='petri'):
        if representation not in REPRESENTATIONS:
            raise ValueError('Representación desconocida: usa petri o bpmn.')
        experiment = self.store.get_experiment(experiment_id)
        solutions = self.store.get_experiment_solutions(experiment_id, 'all')
        if not solutions or len(solutions) > 500:
            raise ValueError('La exploración admite entre 1 y 500 individuos finales.')
        originals = self.store.get_original_artifacts(experiment_id)
        # Source validation occurs before publishing an analysis job.
        models = prepare_models(solutions, originals)
        key = digest({'version': VERSION, 'representation': representation, 'solutions': solutions,
                      'originals': {k: digest(v) for k, v in originals.items()}})
        cached = self.store.find_exploration(experiment_id, key)
        if cached:
            return cached
        with self._lock:
            for eid, active in self._active.items():
                if active['key'] == key and active['experiment_id'] == experiment_id:
                    return {'exploration_id': eid, 'experiment_id': experiment_id, 'status': 'running'}
            if not self._slots.acquire(blocking=False):
                raise ExplorationBusy('Hay otro análisis en curso. Espera a que termine o cancélalo.')
            eid = str(uuid.uuid4())
            event = threading.Event()
            base = {'phase': 'Preparación', 'experiment_name': experiment['experiment_name'], 'population_size': len(models), 'representation': representation}
            try:
                self.store.save_exploration(eid, experiment_id, key, 'running', base)
            except Exception:
                self._slots.release()
                raise
            self._active[eid] = {'key': key, 'experiment_id': experiment_id, 'cancel': event}
            threading.Thread(target=self._run, args=(eid, experiment_id, key, models, event, base), daemon=True, name='model-exploration').start()
        return {'exploration_id': eid, 'experiment_id': experiment_id, 'status': 'running'}

    def _run(self, eid, experiment_id, key, models, event, base):
        def progress(phase):
            self.store.save_exploration(eid, experiment_id, key, 'running', {**base, 'phase': phase})
        try:
            if base['representation'] == 'petri':
                result = analyze(models, event.is_set, progress)
            else:
                result = analyze(models, event.is_set, progress, representation=base['representation'])
            if event.is_set():
                raise InterruptedError('Exploración cancelada.')
            self.store.save_exploration(eid, experiment_id, key, 'completed', {**base, **result, 'phase': 'Completado'})
        except Exception as exc:
            try:
                self.store.save_exploration(eid, experiment_id, key, 'cancelled' if isinstance(exc, InterruptedError) else 'failed', {**base, 'error': str(exc)})
            except Exception:
                # The source experiment may have been explicitly deleted meanwhile.
                pass
        finally:
            with self._lock:
                self._active.pop(eid, None)
            self._slots.release()

    def get(self, eid):
        result = self.store.get_exploration(eid)
        with self._lock:
            orphan = result['status'] == 'running' and eid not in self._active
        if orphan:
            # A restart interrupts a worker, but completed views survive restarts.
            result.update(status='failed', error='El servicio se reinició durante el análisis. Inicia un análisis nuevo.')
            self.store.save_exploration(eid, result['experiment_id'], result['cache_key'], result['status'],
                                        {k: v for k, v in result.items() if k not in ('exploration_id', 'experiment_id', 'cache_key', 'status')})
        return result

    def cancel(self, eid):
        result = self.get(eid)
        with self._lock:
            active = self._active.get(eid)
            if active:
                active['cancel'].set()
        return {'exploration_id': eid, 'status': 'cancelling' if active else result['status']}
