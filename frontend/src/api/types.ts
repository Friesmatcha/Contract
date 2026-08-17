export interface CursorPage<T> {
  items: T[]
  next_cursor: string | null
  has_more: boolean
}

export interface SafeDisplayError {
  message: string
  requestId?: string
}
