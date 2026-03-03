import { useEffect, useMemo, useRef, useState } from 'react'

export default function FancySelect({
  ariaLabel,
  disabled = false,
  onChange,
  options = [],
  placeholder = 'Selecciona...',
  value,
}) {
  const rootRef = useRef(null)
  const [open, setOpen] = useState(false)

  const selected = useMemo(() => options.find((item) => item.value === value) || null, [options, value])

  useEffect(() => {
    function handlePointerDown(event) {
      if (!rootRef.current) return
      if (rootRef.current.contains(event.target)) return
      setOpen(false)
    }

    document.addEventListener('mousedown', handlePointerDown)
    document.addEventListener('touchstart', handlePointerDown)
    return () => {
      document.removeEventListener('mousedown', handlePointerDown)
      document.removeEventListener('touchstart', handlePointerDown)
    }
  }, [])

  function selectValue(nextValue) {
    onChange(nextValue)
    setOpen(false)
  }

  function handleTriggerKeyDown(event) {
    if (disabled) return

    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      const currentIndex = options.findIndex((item) => item.value === value)
      const fallback = 0
      const fromIndex = currentIndex >= 0 ? currentIndex : fallback
      const delta = event.key === 'ArrowDown' ? 1 : -1
      const nextIndex = Math.max(0, Math.min(options.length - 1, fromIndex + delta))
      if (options[nextIndex]) {
        selectValue(options[nextIndex].value)
      }
      return
    }

    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      setOpen((previous) => !previous)
      return
    }

    if (event.key === 'Escape') {
      setOpen(false)
    }
  }

  return (
    <div className={disabled ? 'fancy-select is-disabled' : 'fancy-select'} ref={rootRef}>
      <button
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-label={ariaLabel}
        className="fancy-select-trigger"
        disabled={disabled}
        onClick={() => setOpen((previous) => !previous)}
        onKeyDown={handleTriggerKeyDown}
        type="button"
      >
        <span className={selected ? 'fancy-select-value' : 'fancy-select-placeholder'}>
          {selected ? selected.label : placeholder}
        </span>
        <span aria-hidden="true" className={open ? 'fancy-select-chevron is-open' : 'fancy-select-chevron'}>
          ▾
        </span>
      </button>

      {open && !disabled ? (
        <div className="fancy-select-menu" role="listbox">
          {options.map((item) => {
            const isActive = item.value === value
            return (
              <button
                aria-selected={isActive}
                className={isActive ? 'fancy-select-option is-active' : 'fancy-select-option'}
                key={item.value}
                onClick={() => selectValue(item.value)}
                role="option"
                type="button"
              >
                {item.label}
              </button>
            )
          })}
        </div>
      ) : null}
    </div>
  )
}
