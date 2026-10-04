#!/usr/bin/env python3
"""Bounded native stress campaigns; records every duplicate evaluation separately.

Uses the packaged service and starts/stops only its own JVM. Product sources
are untouched. Native failures and scientific mismatches are separate findings.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import itertools
import json
import logging
import os
from pathlib import Path
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from types import SimpleNamespace
from unittest.mock import patch
from xml.sax.saxutils import quoteattr
import xml.etree.ElementTree as ET

import numpy as np
import requests
from reproduce_seed import ROOT, start_service, scientific_state, ProcessSamples
from api.manager_runtime import execute_job
from execution_control import ExecutionControl
from java_service_client import ProMServiceClient

METRICS = ['fitness','precision','simplicity','generalisation']

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),
                                    allow_nan=False).encode()).hexdigest()

def write_log(path, traces, lifecycle=False):
    content=['<?xml version="1.0" encoding="UTF-8"?><log xes.version="1.0" '
             'xmlns="http://www.xes-standard.org/">']
    for trace in traces:
        content.append('<trace>')
        for label in trace:
            stages=('start','complete') if lifecycle else ('complete',)
            for stage in stages:
                content.append('<event><string key="concept:name" value='+quoteattr(label)+
                    '/><string key="lifecycle:transition" value='+quoteattr(stage)+'/></event>')
        content.append('</trace>')
    path.write_text(''.join(content)+'</log>')
    return str(path)

def fixtures(output):
    directory=output/'logs'; directory.mkdir(exist_ok=True)
    traces={
        'sequence':[list('SABCE')]*8,
        'parallel':[['S',*p,'E'] for p in itertools.permutations('ABCD')],
        'choice':[list(t) for t in ('SABE','SACE','SADE','SABCE','SACBE')]*3,
        'loops':[list(t) for t in ('SAAE','SABABE','SACACE','SABCAE','SABCBCAE','SAE')]*3,
        'alternative_ends':[list(t) for t in ('SAB','SAC','SADB','SADC')]*4,
        'unicode':[['inicio','á & < >','1','fin'],['inicio','活动','1','fin'],
                   ['inicio','1','á & < >','fin']]*4,
        'lifecycle':[list(t) for t in ('SABCE','SACBE','SACE','SABE')]*4,
        'frequency_ties':[list(t) for t in ('SABE','SACE','SBCE','SBAE','SCAE','SCBE')]*3,
        'empty':[], 'empty_trace':[[],[]], 'singleton':[['A']]*3,
    }
    result={name:write_log(directory/(name+'.xes'),value,name=='lifecycle')
            for name,value in traces.items()}
    for seed in range(12):
        rng=random.Random(seed)
        value=[['S',*[rng.choice('ABCDE') for _ in range(rng.randint(2,10))],'E']
               for _ in range(20)]
        result['random_'+str(seed)]=write_log(directory/f'random_{seed}.xes',value)
    return result

def miner(key, variant, parameters):
    return {'key':key,'family':key,'variant':variant,'parameters':parameters}

def miners():
    result=[miner('alpha',name,{'alpha_version':version})
            for name,version in [('Alpha','CLASSIC'),('Alpha+','PLUS'),
                                 ('Alpha++','PLUS_PLUS'),('AlphaR','ROBUST')]]
    result += [miner('inductive',name,{'noise_threshold':.2,'is_debug':False,
                                      'use_multithreading':True}) for name in [
        'Inductive Miner (IM)','Inductive Miner - infrequent (IMf)',
        'Inductive Miner - life cycle (IMlc)',
        'Inductive Miner - infrequent & life cycle (IMflc)',
        'Inductive Miner - partial traces (IMpt)',
        'Inductive Miner - infrequent & partial traces (IMfpt)',
        'Inductive Miner - infrequent & partial traces Ali (IMfpta)']]
    hm={'relative_to_best_threshold':.05,'positive_observation_threshold':1,
        'dependency_threshold':.9,'l1l_threshold':.9,'l2l_threshold':.9,
        'long_distance_threshold':.9,'dependency_divisor':1,'and_threshold':.1,
        'extra_info':False,'use_all_connected_heuristics':True,
        'use_long_distance_dependency':False,'check_best_against_l2l':True}
    result += [miner('heuristics',name,copy.deepcopy(hm))
               for name in ('Heuristics Miner','Flexible Heuristics Miner')]
    result += [miner('split','Split Miner',{'epsilon':.5,'eta':.5})]
    return result

def preprocessings():
    def item(key,params): return {'key':key,'method':key,'variant':key,'parameters':params}
    return [None,item('matrix_filter',{'probability_of_removal_mf':.15,'subsequence_length_mf':2}),
        item('repair_log_filter',{'probability_of_removal_rl':.15,'subsequence_length_rl':2}),
        item('variant_filter',{'keep_threshold_vf':50}),
        item('projection_filter',{'keep_threshold_p':50})]

def cases_for(group,logs):
    cases=[]
    def add(name,log,m,pre=None,mode='replay-token',metrics=METRICS):
        cases.append({'case':name,'log':log,'pipeline':{'miner':m,'preprocessing':pre},
                      'mode':mode,'metrics':metrics})
    mm,pp=miners(),preprocessings()
    if group=='native':
        normal=[k for k in logs if k not in ('empty','empty_trace','singleton') and not k.startswith('random_')]
        for name in normal:
            for i,m in enumerate(mm):
                for j,pre in enumerate(pp):add(f'{name}/m{i}/p{j}',logs[name],m,pre)
        for name in ['empty','empty_trace','singleton']:
            for i,m in enumerate(mm):add(f'{name}/m{i}',logs[name],m)
        for name in normal+[f'random_{s}' for s in range(12)]:
            for epsilon,eta in [(0.,0.),(0.,1.),(1.,0.),(1.,1.),(.5,.5)]:
                add(f'{name}/split/{epsilon}/{eta}',logs[name],miner('split','Split Miner',{'epsilon':epsilon,'eta':eta}))
        for name in ['loops','parallel','frequency_ties']:
            for j,pre in enumerate(pp[1:]):
                for boundary in (0,100) if j>=2 else (0.,1.):
                    p=copy.deepcopy(pre); key=next(k for k in p['parameters'] if 'probability' in k or 'keep' in k)
                    p['parameters'][key]=boundary
                    add(f'{name}/filter{j}/boundary{boundary}',logs[name],mm[-1],p)
        for name in ['loops','parallel','alternative_ends']:
            for i in (5,11,12):
                for boundary in (0.,1.):
                    m=copy.deepcopy(mm[i]);key='noise_threshold' if i==5 else 'dependency_threshold'
                    m['parameters'][key]=boundary;add(f'{name}/m{i}/threshold{boundary}',logs[name],m)
    elif group=='external':
        ilp=miner('ilp','Petri Net ILP',{'solver_type':'JAVAILP_LPSOLVE','search_type':'PER_CD','separate_initial_places':True})
        hybrid=miner('hybrid_ilp','Hybrid ILPMiner',{'lp_objective':'Minimize Arcs','lp_variable_type':'Two variables per event',
                                                'lp_filter':'None','discovery_strategy':'Directly Follows'})
        for name in ['sequence','choice','loops']:
            for i,m in enumerate([ilp,hybrid]):add(f'{name}/solver{i}',logs[name],m)
        for name in ['sequence','choice']:
            for mode in ['replay','alignment']:
                for i in [0,5,13]:add(f'{name}/m{i}/{mode}',logs[name],mm[i],mode=mode)
    elif group=='targeted':
        pre=pp[3].copy();pre['parameters']={'keep_threshold_vf':61}
        for eta in [.514416009274668,.968100686624893]:
            add(f'financial/{eta}',str(ROOT/'event_logs/BPI_Challenge_2012.xes'),
                miner('split','Split Miner',{'epsilon':.1759048310940582,'eta':eta}),pre)
        pre=pp[1].copy();pre['parameters']={'probability_of_removal_mf':.0825134494733932,'subsequence_length_mf':2}
        add('hospital/known',str(ROOT/'event_logs/Hospital Billing - Event Log.xes'),
            miner('split','Split Miner',{'epsilon':.7442672416590299,'eta':.5113948325303002}),pre)
    return cases

def native_signature(status,body):
    if status!=200: return {'status':status,'error':body.get('error'),'message':body.get('message')}
    if not body.get('model_semantic_sha256'): raise AssertionError('Missing semantic model identity')
    keys=['model_semantic_sha256','metrics','metrics_status','is_feasible','constraint_violations',
          'visible_transition_count','model_schema_version','discovery_metadata','evaluation_policy_version']
    return {key:body.get(key) for key in keys}

def stop(process,handle,samples):
    process.terminate()
    try: process.wait(timeout=5)
    except Exception: process.kill();process.wait(timeout=5)
    handle.close(); samples.close()

def native_campaign(args):
    logs=fixtures(args.output);cases=cases_for(args.group,logs)
    (args.output/'cases.json').write_text(json.dumps(cases,indent=2))
    report={'group':args.group,'case_count':len(cases),'rounds':[],'mismatches':[], 'errors':[]}
    reference={};round0_environment=None;total_start=time.monotonic()
    for round_id,workers in enumerate((1,8,4)):
        directory=args.output/f'round-{round_id}';directory.mkdir(exist_ok=True)
        process,handle,url=start_service(args,directory);samples=ProcessSamples(process.pid)
        timer=threading.Timer(args.round_seconds,process.kill);timer.start()
        results=[];lock=threading.Lock();sequence=list(cases)
        random.Random(917+round_id).shuffle(sequence)
        # Exact duplicate calls remain individual rows and must all agree.
        if round_id:sequence+=sequence[:min(24,len(sequence))]
        started=time.monotonic()
        def evaluate(case):
            before=time.monotonic()
            payload={'experiment_id':'stress','log_path':case['log'],'pipeline':case['pipeline'],
                     'metrics':case['metrics'],'conformance_mode':case['mode']}
            response=requests.post(url+'/pipeline',json=payload,timeout=args.request_seconds)
            body=response.json();signature=native_signature(response.status_code,body)
            row={'case':case['case'],'seconds':time.monotonic()-before,'status':response.status_code,
                 'signature':signature,'response':body}
            with lock:
                with (directory/'responses.jsonl').open('a') as f:f.write(json.dumps(row,sort_keys=True)+'\n')
            return row
        try:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures=[pool.submit(evaluate,case) for case in sequence]
                for future in as_completed(futures):
                    row=future.result();results.append(row);key=row['case'];signature=row['signature']
                    if round_id==0:reference[key]=signature
                    elif signature!=reference[key]:report['mismatches'].append({'round':round_id,'case':key,'reference':reference[key],'actual':signature})
                    if row['status']!=200:report['errors'].append({'round':round_id,'case':key,'signature':signature})
                    if row['status']==200:
                        environment=row['response'].get('evaluation_environment')
                        if round0_environment is None:round0_environment=environment
                        elif environment!=round0_environment:raise AssertionError('Environment changed between JVMs')
            # Replay a subset inside this JVM/experiment to exercise warm caches.
            warm=[evaluate(case) for case in cases[:min(20,len(cases))]]
            for row in warm:
                if row['signature']!=reference[row['case']]:report['mismatches'].append({'round':round_id,'warm':True,'case':row['case'],'reference':reference[row['case']],'actual':row['signature']})
            report['rounds'].append({'round':round_id,'workers':workers,'evaluations':len(results)+len(warm),
                'seconds':time.monotonic()-started,'resources':samples.summary(started,time.monotonic())})
        except Exception as error:
            report['aborted']={'round':round_id,'error':str(error),'completed':len(results)}
        finally:
            timer.cancel();stop(process,handle,samples)
            report['seconds']=time.monotonic()-total_start
            (args.output/'report.json').write_text(json.dumps(report,indent=2))
            print(json.dumps({k:v for k,v in report.items() if k not in ('mismatches','errors')}),flush=True)
        if 'aborted' in report:break
    if report['mismatches'] or 'aborted' in report:sys.exit(1)
    print(f"PASS deterministic comparisons; {len(report['errors'])} native error responses recorded separately",flush=True)

def search_configs(logs):
    cases=[]
    for seed in [0,1,42,2**32,2**53-1]:
        cases.append({'name':f'seed-{seed}','log':logs['parallel'],'seed':seed,'population':12,'evaluations':60,'partitions':2,'metrics':METRICS})
    for name,population,partitions,metrics in [
        ('one-objective',4,1,['fitness']),('two-objectives',4,3,['fitness','precision']),
        ('three-objectives',10,2,METRICS[:3]),('few-directions',4,1,METRICS),
        ('many-directions',12,5,METRICS),('large-population',24,2,METRICS),
        ('structural',12,2,['t_edges','cfc','elc']),('metric-order',12,2,list(reversed(METRICS)))]:
        cases.append({'name':name,'log':logs['loops'],'seed':42,'population':population,
                      'evaluations':population*4,'partitions':partitions,'metrics':metrics})
    for name in ['alternative_ends','lifecycle','unicode','frequency_ties','random_3','random_11']:
        cases.append({'name':name,'log':logs[name],'seed':1,'population':12,'evaluations':60,'partitions':2,'metrics':METRICS})
    cases.append({'name':'sepsis-full','log':str(ROOT/'event_logs/Sepsis Cases - Event Log.xes'),
                  'seed':7,'population':12,'evaluations':60,'partitions':3,'metrics':METRICS})
    return cases

def real_prefix_configs(output, count):
    """One fixed sampling rule for every repository log; no per-log tuning."""
    directory=output/'real-prefix';directory.mkdir(exist_ok=True);cases=[]
    ET.register_namespace('', 'http://www.xes-standard.org/')
    for source in sorted((ROOT/'event_logs').glob('*.xes')):
        selected=ET.Element('{http://www.xes-standard.org/}log',{'xes.version':'1.0'})
        traces=0
        with source.open('rb') as stream:
            for event,node in ET.iterparse(stream,events=('end',)):
                if node.tag.rsplit('}',1)[-1]=='trace':
                    selected.append(node);traces+=1
                    if traces>=count:break
        destination=directory/source.name
        ET.ElementTree(selected).write(destination,encoding='utf-8',xml_declaration=True)
        for seed in (0,2**53-1):
            cases.append({'name':source.stem.replace(' ','_')+'-'+str(seed),'log':str(destination),
                          'seed':seed,'population':8,'evaluations':32,'partitions':2,'metrics':METRICS,
                          'source_log':str(source),'trace_limit':count,'sample_trace_count':traces})
    return cases

def searches(args):
    logs=fixtures(args.output)
    cases=real_prefix_configs(args.output,args.real_prefix) if args.real_prefix else search_configs(logs)
    (args.output/'cases.json').write_text(json.dumps(cases,indent=2))
    directory=args.output/'service';directory.mkdir(exist_ok=True)
    process,handle,url=start_service(args,directory);samples=ProcessSamples(process.pid)
    timer=threading.Timer(args.round_seconds,process.kill);timer.start();report={'cases':[]};record_lock=threading.Lock()
    os.environ['OPT_MAX_EVALUATION_WORKERS']='8'
    # Every logical attempt belongs to a job; a shared trace is safe for concurrent jobs.
    os.environ['OPT_EVALUATION_TRACE_FILE']=str(args.output/'logical-evaluations.jsonl')
    original=ProMServiceClient.evaluate_pipeline
    def record(client,*a,**kw):
        row={'job':client.experiment_id,'pipeline':kw.get('pipeline',a[1] if len(a)>1 else None)}
        try:result=original(client,*a,**kw);row['response']=result;return result
        except Exception as error:row['error']=str(error);raise
        finally:
            with record_lock:
                with (args.output/'physical-evaluations.jsonl').open('a') as f:f.write(json.dumps(row,sort_keys=True)+'\n')
    def run(case,index):
        job=f"{args.worker}/{case['name']}/{index}";control=ExecutionControl()
        manager=SimpleNamespace(_lock=threading.Lock(),_subscribers={},java_service_timeout_seconds=args.request_seconds,
            _jobs={job:{'job_id':job,'status':'running','_control':control,'progress':{'evaluations_done':0,'max_evaluations':case['evaluations']}}})
        config={'execution_name':job,'log_path':case['log'],'service_url':url,'metrics':case['metrics'],
                'excluded_miners':['ilp','hybrid_ilp'],'conformance_mode':'replay-token',
                'discover':{'seed':case['seed'],'population_size':case['population'],'max_evaluations':case['evaluations'],
                            'n_partitions':case['partitions'],'n_workers':args.worker}}
        started=time.monotonic();result=execute_job(manager,job,config);state=scientific_state(result)
        (args.output/(case['name']+f'-{index}-state.json')).write_text(json.dumps(state,indent=2,allow_nan=False))
        return {'name':case['name'],'job':job,'index':index,'seconds':time.monotonic()-started,'digest':digest(state),
                'counts':result['counts'],'optimizer_config':result['optimizer_config'],'log_sha256':result['log_sha256'],
                'optimizer_source_sha256':result['optimizer_source_sha256']}
    try:
        with patch.object(ProMServiceClient,'evaluate_pipeline',record):
            # First run is sequential across jobs; repeats overlap separate optimizers.
            expected={}
            for case in cases:
                try:r=run(case,0);expected[case['name']]=r;report['cases'].append(r)
                except Exception as error:report['cases'].append({'name':case['name'],'error':str(error),'index':0})
                (args.output/'report.json').write_text(json.dumps(report,indent=2))
            with ThreadPoolExecutor(max_workers=3) as pool:
                future_cases={pool.submit(run,c,1):c for c in cases if c['name'] in expected}
                for future in as_completed(future_cases):
                    case=future_cases[future]
                    try:
                        r=future.result();r['matches_reference']=r['digest']==expected[case['name']]['digest'];report['cases'].append(r)
                    except Exception as error:report['cases'].append({'name':case['name'],'error':str(error),'index':1})
                    (args.output/'report.json').write_text(json.dumps(report,indent=2))
    finally:
        timer.cancel();stop(process,handle,samples)
    failures=[r for r in report['cases'] if 'error' in r or r.get('matches_reference') is False]
    print(json.dumps({'searches':len(report['cases']),'failures':len(failures),'python_hash_seed':os.getenv('PYTHONHASHSEED'),'workers':args.worker}),flush=True)
    if failures:sys.exit(1)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--group',choices=['native','external','targeted','search'],required=True)
    parser.add_argument('--java',default='/usr/lib/jvm/java-8-openjdk-amd64/bin/java')
    parser.add_argument('--heap-gb',type=int,default=8)
    parser.add_argument('--admission-workers',type=int,default=8)
    parser.add_argument('--service-classes',type=Path,default=ROOT/'src/mining-service/target/prom-service-0.1.0.jar')
    parser.add_argument('--request-seconds',type=int,default=20)
    parser.add_argument('--round-seconds',type=int,default=240)
    parser.add_argument('--worker',type=int,default=1)
    parser.add_argument('--real-prefix',type=int,default=0)
    args=parser.parse_args();args.output=args.output.resolve();args.output.mkdir(parents=True,exist_ok=True)
    logging.disable(logging.CRITICAL)
    if args.group=='search':searches(args)
    else:native_campaign(args)
