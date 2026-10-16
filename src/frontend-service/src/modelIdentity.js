// Existing model digest, not the pipeline fingerprint or a hash of its metrics.
export function modelIdentity(item, solutionId, population = []) {
  const digest = typeof item.model_semantic_sha256 === 'string' && /^[a-f0-9]{64}$/i.test(item.model_semantic_sha256)
    ? item.model_semantic_sha256.toLowerCase() : null
  let length = 10
  if (digest) while (length < digest.length && population.some(other => {
    const hash = typeof other.model_semantic_sha256 === 'string' ? other.model_semantic_sha256.toLowerCase() : null
    return hash && hash !== digest && hash.startsWith(digest.slice(0, length))
  })) length++
  const shortDigest = digest ? digest.slice(0, length) : null
  return { modelDigest: digest, shortDigest, label: `Solution #${solutionId} ${shortDigest || '(sin digest)'}` }
}
