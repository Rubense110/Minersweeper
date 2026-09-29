import { finalMarkingsFor, markingEntries } from '../petriMarkings'

function MarkingContents({ marking, places }) {
  const entries = markingEntries(marking, places)
  if (entries.length === 0) return <span className="muted">∅ (0 tokens)</span>
  return (
    <span className="marking-entries">
      {entries.map(({ placeId, label, tokens }) => (
        <span className="marking-entry" key={placeId}>
          {label === placeId ? <code>{placeId}</code> : <>{label} <code>({placeId})</code></>}
          <span className="marking-token-count">× {tokens}</span>
        </span>
      ))}
    </span>
  )
}

export default function PetriMarkings({ petri, selectedFinalIndex = 0, onSelectFinal }) {
  const places = petri?.places || []
  const finals = finalMarkingsFor(petri)

  return (
    <section className="petri-markings" aria-label="Petri net markings">
      <div className="marking-row">
        <strong><span className="marking-key initial" />Initial marking</strong>
        <MarkingContents marking={petri?.initial_marking} places={places} />
      </div>
      <div className="marking-row">
        <strong><span className="marking-key final" />Final markings ({finals.length})</strong>
        {finals.length === 0 ? <span className="muted">Not available</span> : (
          <div className="marking-final-list">
            {finals.map((marking, index) => (
              <button
                aria-label={`Show final marking ${index + 1} of ${finals.length}`}
                aria-pressed={index === selectedFinalIndex}
                className={index === selectedFinalIndex ? 'marking-final-option active' : 'marking-final-option'}
                key={index}
                onClick={() => onSelectFinal(index)}
                type="button"
              >
                <span className="marking-final-number">#{index + 1}</span>
                <MarkingContents marking={marking} places={places} />
              </button>
            ))}
          </div>
        )}
      </div>
      <p className="small muted marking-legend">Blue places contain initial tokens; green outlines mark the selected final state. Each final is an alternative, not an additional set of tokens.</p>
    </section>
  )
}
