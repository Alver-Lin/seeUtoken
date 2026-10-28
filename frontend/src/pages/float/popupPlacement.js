/** Keep the popup inside the window and its tail clear of the rounded corners. */
export function popupPlacement({ centerY, popupHeight, baseTop, viewportHeight, radius = 36, padding = 18 }) {
  const top = Math.max(padding, Math.min(viewportHeight - padding - popupHeight, centerY - popupHeight / 2));
  // CSS triangle and native glass both use a 12px half-height for the tail.
  const inset = Math.min(popupHeight / 2, radius + 12);
  const tailTop = Math.max(inset, Math.min(popupHeight - inset, centerY - top));
  return { offsetY: top - baseTop, tailTop };
}
