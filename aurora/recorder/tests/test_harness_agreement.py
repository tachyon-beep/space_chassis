import chassis
import recorder_streams


def test_the_harness_and_the_recorder_agree_on_reasoning_effort_levels():
    # Held back from plan 1: the harness's chassis sends a reasoning effort only from this list,
    # and the recorder composes declared streams from its own copy of it.
    assert chassis.REASONING_EFFORT_LEVELS == recorder_streams.REASONING_EFFORT_LEVELS
    assert "minimal" in chassis.REASONING_EFFORT_LEVELS
