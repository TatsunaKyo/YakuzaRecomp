#!/usr/bin/env python3
"""Keep the host event loop from waiting on GS producer/debug locks."""
import hashlib
from prepare_game import require

GS_FRONTEND_SHA256 = "4c6e6391972ecaafd18bf3e3e047ef980b4cd0907c8199a52cb9d98d8b7397b8"


def adapt_presentation(data):
    data = data.replace(b"\r\n", b"\n")
    require(hashlib.sha256(data).hexdigest() == GS_FRONTEND_SHA256,
            "Unsupported GS frontend; reassess host presentation locking")
    text = data.decode()
    start = text.index("void GS::latchHostPresentationFrame()\n{")
    end = text.index("\nbool GS::copyLatchedHostPresentationFrame", start)
    body = text[start:end]
    state_lock = "        std::lock_guard<std::recursive_mutex> lock(m_stateMutex);"
    require(body.count(state_lock) == 2, "Presentation state locks differ")
    body = body.replace(state_lock, """        // Keep the last completed frame while a producer owns the GS. The
        // window thread must still pump events and sample host input.
        std::unique_lock<std::recursive_mutex> lock(m_stateMutex, std::try_to_lock);
        if (!lock.owns_lock())
            return;""", 1)
    backend_lock = "        std::lock_guard<std::mutex> backendLock(m_backendLifetimeMutex);"
    require(body.count(backend_lock) == 1, "Presentation backend lock differs")
    body = body.replace(backend_lock, """        std::unique_lock<std::mutex> backendLock(m_backendLifetimeMutex, std::try_to_lock);
        if (!backendLock.owns_lock())
            return;""")
    old = state_lock + "\n        recordPresentDebugEventUnlocked(displayFbp, sourceFbp, width, height, usedPreferred);"
    new = """        // A diagnostic history entry must not hold up an already ready frame.
        std::unique_lock<std::recursive_mutex> lock(m_stateMutex, std::try_to_lock);
        if (lock.owns_lock())
            recordPresentDebugEventUnlocked(displayFbp, sourceFbp, width, height, usedPreferred);"""
    require(body.count(old) == 1, "Presentation debug lock differs")
    body = body.replace(old, new)
    return (text[:start] + body + text[end:]).encode()
