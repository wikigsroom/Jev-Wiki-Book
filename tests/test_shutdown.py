import threading

import pytest

from jev_core.storage import Cancelled, IndexJobs


def test_shutdown_waits_for_index_worker_and_rejects_new_jobs(tmp_path):
    entered, release, stopped = threading.Event(), threading.Event(), threading.Event()

    class Store:
        def build(self, root, progress, cancel, **kwargs):
            entered.set()
            assert release.wait(5)
            assert cancel.is_set()
            raise Cancelled("cancelled")

    jobs = IndexJobs(Store())
    jobs.start(str(tmp_path))
    assert entered.wait(2)

    def close():
        jobs.close()
        stopped.set()

    closer = threading.Thread(target=close)
    closer.start()
    try:
        assert jobs.cancel_event.wait(2)
        assert not stopped.is_set()
        with pytest.raises(RuntimeError, match="关闭"):
            jobs.start(str(tmp_path))
    finally:
        release.set()
        closer.join(3)
    assert stopped.is_set() and not jobs.thread.is_alive()
    assert jobs.status()["state"] == "cancelled"
