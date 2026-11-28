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
| a thread left running when the test is over (it runs on into the next tests) | end and join every thread a test starts; `no_leaked_threads` (tests/support/guards.py) fails a test that leaves one, with a short allow-list of the program's own threads that end by themselves |
| a process left running when the test is over (a daemon, a stand-in modem holding its ports for hours) | stop what the test starts in a `finally` or by `remember_stop`; `no_leaked_processes` (tests/support/guards.py) ends and fails a test whose processes outlive it (Linux), the end of a worker's session and a test over its time limit end what is left, and the stand-ins end by themselves when the run's process is gone (`children.end_with_the_run`) |
| a helper that returns when the first of two things is there, read for the second | wait for what the test reads (`launch` waits for the window's loop) |
| a test that needs state another left (the order) | each test makes its own; the gate runs the suite in a random order (pytest-randomly), seed printed |

## The log

| date | run | test | first failing line | cause | mend |
|---|---|---|---|---|---|
| 2026-11-28 | ci 46108297365 attempt 1 (Linux, master) | `test_desktop_webshell::test_on_macos_the_window_is_wkwebviews_and_the_trays_calls_go_to_the_main_thread` | `rig.toolkits.started == []` at line 1383, and a thread's `the window loop runs until the window is destroyed` | the shell starts the tray before its window loop, and `launch` returned on the tray: a test read the toolkit before the loop started; failing, it left its shell thread running for 60 s, which then ran into the next tests (the GTK path, `No module named 'gi'`). Shown every time with the window loop started 0.5 s late: 17 of the file's tests failed so | `launch` waits for the loop of a window that was made, one test that starts its own thread too; a guard of the suite (`no_leaked_threads`, tests/support/guards.py) fails a test that leaves a thread running after its teardown; the desktop tests that did were mended |
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
| 2026-11-28 | ci 46100554085 (Linux) | `test_check_script::test_a_signal_the_parent_ignores_or_blocks_leaves_the_run_going_and_the_others_still_end_everything[blocked]` | `TimeoutExpired: ... timed out after 30 seconds` | not found yet: the gate with HUP and TERM blocked did not end within 30 s of its INT, once in a shuffled order; it passed in the other runs here and there | quarantined 2026-11-28 (nightly); to be mended or rewritten by round 22 |
| 2026-11-28 | ci 46102490407 (Linux), seed 585423670 | `test_desktop_webshell::test_the_close_button_hides_the_window_while_the_desktop_has_a_tray_and_quits_when_it_has_none` | `assert (not True)` after `thread.join(60)` | the same as the first row | the same; the quarantine is lifted |
| 2026-11-28 | ci 46106254112 (Windows) | `test_local_settings::test_this_computer_changes_them_and_runs_the_test` | `no alert_result message came` | the page's `expect` gave up after 5 s while the alert command, a process of its own, started on a busy runner | the helpers' waits for what a test expects (`expect`, `recv`, `frames`, `said`, `heard`, `connected`, `wait_gone`) have the suite's patience |
| 2026-11-28 | ci 46115632980 (Windows) | `test_cross_world::test_the_reply_message_goes_back_through_the_gateway_the_same_way_and_its_ack_follows`; and 4 tests by the new thread guard | `assert (0 == 1)`; `neoaprs-test-loop-nudge` left | the received reply read at the moment its sender saw the ack; the Windows test loops' own nudger, started by the first test of a worker that makes a loop | the reply waited for; the nudger is on the guard's allow-list |
| 2026-11-28 | ci 46117613760 (Windows) | `test_mapauto::test_a_map_that_covers_the_place_is_not_made_again_...` (the thread guard) | `map-cut (in_parallel.<locals>.run)` left | the map cut's workers end their piece after the cut is over, by design (its results are ignored) | on the guard's allow-list |
| 2026-11-28 | ci 46121327078 (Windows) | `test_direwolf_modem::test_a_kiss_port_taken_by_another_program_gives_another_port_and_the_line_is_pointed_at_it` | `the condition did not come true` | this round's mend put the modem's search at a port the system gave, in Windows' range, where 50 ports in a row had no free pair | the port held is the first free one the modem's own search finds in the worker's block |
| 2026-11-28 | here, found by the coordinator | four orphans of test runs alive for up to 33 hours: a daemon of `test_main::test_a_port_that_is_in_use_moves_the_page_...` (port 10135) and stand-in Direwolf children of `test_card_levels::test_a_sound_card_radio_puts_...` (23000), `test_direwolf_driver::test_the_driver_starts_direwolf_...` (21500) and `test_direwolf_modem::test_tune_stops_...` (20000, this round's seed 5) | none: they live on | a test that failed before its own stop never stopped what it started; the one on 21500 was the "other program" of the fixed-port flake of rounds 18 and 20 | the four tests stop in a `finally` or by `remember_stop`; the process guard, the session's end and the stand-ins' own end (row of the forms above); the four orphans are left for the owner |
| 2026-11-28 | ci 46125028240 (Windows) | `test_restart_port::test_the_update_test_finds_the_page_beside_the_port_it_holds_and_the_same_page_after_the_restart` | `assert (49215 == 49216)` | the held port was one the system gave; on Windows another test's daemon served a page beside it | the held port is one of the worker's block |
| 2026-11-28 | seeded run, seed 5, here | `test_direwolf_modem::test_tune_stops_the_radios_direwolf_runs_the_alternating_tones_holds_the_frames_and_starts_it_again_on_its_port` | `4 == 3` (starts of Direwolf) | the KISS port of the worker's block was taken for a moment by another run of the suite on this machine; the modem started again on it, one start more | the count allows the start made again |
| 2026-11-27 | round 18 merge, here | `test_direwolf_modem::test_a_kiss_port_taken_by_another_program_...` | `127.0.0.1:21500` in use | a port of the worker's block bound without a look, held by a program of this machine | round 20: a port the system gives |
