from kinsun.scheduler.fanout import fanout_job


def test_runs_action_for_each_item_and_builds_cron():
    done = []
    job = fanout_job(name="t", hour=8, population=lambda: ["a", "b"], action=done.append)
    job.run()
    assert done == ["a", "b"]
    assert job.name == "t"
    assert job.cron == "0 8 * * *"


def test_minute_in_cron():
    job = fanout_job(name="t", hour=3, minute=30, population=lambda: [], action=lambda x: None)
    assert job.cron == "30 3 * * *"


def test_one_item_failure_isolated():
    done = []

    def action(item):
        if item == "a":
            raise RuntimeError("boom")
        done.append(item)

    fanout_job(name="t", hour=8, population=lambda: ["a", "b"], action=action).run()
    assert done == ["b"]


def test_action_can_skip_via_early_return():
    done = []

    def action(item):
        if item % 2 == 0:
            return
        done.append(item)

    fanout_job(name="t", hour=8, population=lambda: [1, 2, 3, 4], action=action).run()
    assert done == [1, 3]


def test_item_id_used_for_failure_log(caplog):
    import logging

    def action(_item):
        raise RuntimeError("boom")

    with caplog.at_level(logging.ERROR):
        fanout_job(
            name="med",
            hour=8,
            population=lambda: [("e1", ["藥"])],
            action=action,
            item_id=lambda it: it[0],
        ).run()
    assert "e1" in caplog.text
