/** Only one native shape update may be in flight; intermediate layouts expire. */
export function createShapeSender(send) {
  let pending = null;
  let running = false;
  let disposed = false;
  let acknowledged = '';

  async function drain() {
    if (running || disposed) return;
    running = true;
    try {
      while (pending && !disposed) {
        const payload = pending;
        pending = null;
        const key = JSON.stringify(payload);
        if (key === acknowledged) continue;
        try {
          await send(payload);
          acknowledged = key;
        } catch (_) {
          // A later geometry report can retry; don't suppress a failed shape.
        }
      }
    } finally {
      running = false;
    }
  }

  return {
    push(payload) {
      if (disposed) return;
      pending = payload;
      void drain();
    },
    dispose() {
      disposed = true;
      pending = null;
    },
  };
}
