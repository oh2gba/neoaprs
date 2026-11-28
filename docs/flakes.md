# Flaky tests

A flaky test is a fault in a test: it fails on some runs and passes on others with the same code. It
teaches everyone to press "re-run", and the day a real fault fails it, nobody looks.

## The rule

- A red run is never just run again. The test that failed is mended in the same round, or it is
  quarantined: marked `@pytest.mark.nightly("quarantined DATE: why")`, which leaves it out of the gate
  and CI and runs it each night (`.github/workflows/nightly.yml`). A quarantined test not mended
  within two rounds is rewritten or removed.
- Each flake gets a row below when it happens: the run, the test, its first failing line, the cause,
  the mend. `scripts/release --rerun` may run a failed job once, but its log says which test failed,
  and that test gets its row.
- The budget: under 5 % of the runs of any 60 red for a flake, on each system.

## What makes a test flaky here, and the right form

`tests/test_flake_rules.py` refuses the forms it can tell from the source; an exception there needs
an entry with its reason.

| what | the right form |
|---|---|
| a wait for what is expected that gives up within seconds (`until(..., 3.0)`, `wait_for(x, 5)`, `assert done.wait(2)`) | `until(...)` with the suite's patience (`tests/support/patience.py`, 30 s): the wait ends as soon as the thing happens |
| a time slept in a test's body, then a check | `until(...)`, or `poll(...)` outside an event loop; a window in which something must not happen is `idle_for(seconds)` |
| `assert not t.is_alive()` at a moment | `t.join()` first, without a timeout or with a generous one |
| a fixed port | port 0, a port of the worker's block (`tests/support/webports.py`, `modemports.py`), or `free_port(...)` |
| an upper bound on real time near what the code takes | a bound far below what the fault would take and far above a step of a busy runner, or the time measured on `virtual_time` |
| a stand-in that ends by itself after some seconds | it waits for the test's word, with the suite's patience, or for the test's time limit (600 s) |
| a count read after a fixed pause | wait for the count; a pause is only for a check that nothing more came |
| "no WARNING in the log" | `warnings_in(caplog)` (`tests/support/logs.py`): the database's note of a slow disk is the machine's, not the test's |
| a test that needs state another left (the order) | each test makes its own; the gate runs the suite in a random order (pytest-randomly), seed printed |

## The log

| date | run | test | first failing line | cause | mend |
|---|---|---|---|---|---|
| 2026-11-27 | ci 45956742755 (Windows) | `test_desktop_endafter::test_an_app_stuck_for_good_is_ended_from_outside_within_the_bound` | `subprocess.TimeoutExpired` | a child given too little time on a busy runner | `5c728540` |
| 2026-11-27 | ci 45936938612 (Windows) | `test_main::test_the_daemon_on_a_tcp_port_logs_and_keeps_the_capture_and_stops_on_sigterm_in_time` | `tests\test_main.py:364: AssertionError` | the daemon's stop on a busy runner | round 20: the positive waits of the suite given its patience |
| 2026-11-27 | ci 45930009964 (Windows) | `test_mercury_world::test_an_ack_lost_on_its_way_back_is_sent_again_for_the_retry_and_the_message_is_kept_once` | `AssertionError: kept once` | a count read at a moment | `b3bf54d5` |
| 2026-11-27 | ci 45927812631 (Windows) | `test_radio_flows::test_a_stall_restart_a_settings_restart_and_a_stop_at_once_...[stop]` | `assert (0 == 1)` | a stall fed too close to its time | `2ed20b17` |
| 2026-11-26 | ci 45904014008 (Windows) | `test_mercury_world::test_our_frames_wait_while_a_frame_is_on_the_air_...` | `the attempt waits, none is used up` | a wait of 3 s for the busy channel | `0a8c9bb8`; round 20: `until`'s patience |
| 2026-11-26 | ci 45881245150, 45691318058 (Windows) | `test_direwolf_modem::test_the_level_now_comes_ten_times_a_second_...` | a level read at a moment | the end of the level waited for by time | `c88f59de` |
| 2026-11-22 | ci 45015098491 (Linux) | `test_six_radios[...-sound-card-radio]` | a beacon count | a count on a busy runner | round 20: nightly |
| 2026-11-27 | audit, random order | `test_desktop_qt::test_the_window_has_its_title_the_default_size_and_shows_the_page` | the window is 1000 x 700 | one window shared by the file's tests, resized by another | round 20: a window per test |
| 2026-11-28 | ci 46098760909 (Windows) | `test_restart_port::test_the_update_test_finds_the_page_beside_the_port_it_holds_and_the_same_page_after_the_restart` | `assert (51099 == 51100)` | the port after the held one is the system's to hand out on Windows, and was taken; the next test of the worker found the page's request left running | the page is the first free one after the held port |
| 2026-11-28 | ci 46098760909 (Windows) | `test_mercury_modem::test_a_sound_card_gone_while_mercury_runs_ends_the_run_and_is_the_radios_problem_until_it_starts_again` | `the condition did not come true` | the radio's problem shows only between the run's end and the next start, 0.5 s, looked at once a step | a back-off of 2 s and every state seen is kept |
| 2026-11-28 | seeded run, seed 5, here | `test_direwolf_modem::test_tune_stops_the_radios_direwolf_runs_the_alternating_tones_holds_the_frames_and_starts_it_again_on_its_port` | `4 == 3` (starts of Direwolf) | the KISS port of the worker's block was taken for a moment by another run of the suite on this machine; the modem started again on it, one start more | the count allows the start made again |
| 2026-11-27 | round 18 merge, here | `test_direwolf_modem::test_a_kiss_port_taken_by_another_program_...` | `127.0.0.1:21500` in use | a port of the worker's block bound without a look, held by a program of this machine | round 20: a port the system gives |
