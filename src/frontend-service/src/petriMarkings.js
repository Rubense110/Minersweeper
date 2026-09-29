export function finalMarkingsFor(petri) {
  if (Array.isArray(petri?.final_markings) && petri.final_markings.length > 0) {
    return petri.final_markings.filter(Array.isArray)
  }
  return Array.isArray(petri?.final_marking) ? [petri.final_marking] : []
}

export function selectedFinalMarking(petri, index = 0) {
  const markings = finalMarkingsFor(petri)
  return markings[Math.max(0, Math.min(index, markings.length - 1))] ?? null
}

export function markingEntries(marking, places = []) {
  if (!Array.isArray(marking)) return []
  const labels = new Map(places.map((place) => [place.id, place.label || place.id]))
  return marking
    .filter((entry) => entry && Number(entry.tokens) > 0)
    .map((entry) => ({
      placeId: entry.place_id,
      label: labels.get(entry.place_id) || entry.place_id,
      tokens: Number(entry.tokens),
    }))
}

export function markingTokenMap(marking) {
  return new Map(markingEntries(marking).map((entry) => [entry.placeId, entry.tokens]))
}
