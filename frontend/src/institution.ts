import { useCallback, useEffect, useState } from 'react'

/** Every installation is scoped by institution (tenant). See AGENTS.md. */
export const DEFAULT_INSTITUTION = 'university-001'

const STORAGE_KEY = 'mentora.institution'

export function readInstitution(): string {
  try {
    return localStorage.getItem(STORAGE_KEY)?.trim() || DEFAULT_INSTITUTION
  } catch {
    // Storage can be disabled (private mode, hardened browser).
    return DEFAULT_INSTITUTION
  }
}

export function writeInstitution(value: string): void {
  try {
    localStorage.setItem(STORAGE_KEY, value)
  } catch {
    // Non-fatal: the value still applies to the page that is open.
  }
}

/** Read the stored course so the library page reopens where the teacher left off. */
export function readSelectedCourse(): string {
  try {
    return localStorage.getItem('mentora.course') ?? ''
  } catch {
    return ''
  }
}

export function writeSelectedCourse(value: string): void {
  try {
    localStorage.setItem('mentora.course', value)
  } catch {
    // Non-fatal.
  }
}

/**
 * The tenant, shared by every page.
 *
 * The Teacher Studio is a page of its own and is routinely opened in a second
 * tab (it is the large-screen slide view), so the tenant cannot live in one
 * page's state. It is persisted and kept in step across tabs through the
 * `storage` event.
 */
export function useInstitution(): [string, (value: string) => void] {
  const [institution, setInstitution] = useState<string>(readInstitution)

  const update = useCallback((value: string) => {
    setInstitution(value)
    writeInstitution(value)
  }, [])

  useEffect(() => {
    function onStorage(event: StorageEvent) {
      if (event.key === STORAGE_KEY) setInstitution(readInstitution())
    }
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [])

  return [institution, update]
}
