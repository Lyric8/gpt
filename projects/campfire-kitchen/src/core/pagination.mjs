/** Bounded catalog pages: all records stay searchable, only a page enters the DOM. */
export const PAGE_SIZE = 24;
export function paginate(items, requested = 1, size = PAGE_SIZE) {
  if (!Array.isArray(items) || !Number.isInteger(size) || size < 1) throw new TypeError('Invalid pagination input');
  const pages = Math.max(1, Math.ceil(items.length / size));
  const page = Math.max(1, Math.min(pages, Number.isFinite(requested) ? Math.trunc(requested) : 1));
  const offset = (page - 1) * size;
  return {items:items.slice(offset, offset + size), page, pages, total:items.length, first:items.length?offset+1:0, last:Math.min(offset+size, items.length)};
}
