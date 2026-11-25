"""Tests for the maximum run time and the fault event."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from aioescea import EsceaConnectionError
from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
    async_fire_time_changed,
)

from custom_components.escea_fireplace.const import (
    CONF_GENERATION,
    CONF_MAX_RUN_HOURS,
    CONF_SERIAL,
    DOMAIN,
    EVENT_AUTO_OFF,
    GEN3,
)
from homeassistant.const import CONF_HOST, STATE_UNKNOWN
from homeassistant.core import HomeAssistant

from .conftest import G3_HOST, FakeG3

FAULT = "event.escea_654321_fault"
OFF = {"on": "false"}


@pytest.fixture(autouse=True)
def no_gap() -> None:
    with patch("aioescea.ncapi.MIN_REQUEST_GAP", 0):
        yield


async def _setup(hass: HomeAssistant, hours: int = 0) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="654321",
        title="Escea 654321",
        data={CONF_HOST: G3_HOST, CONF_SERIAL: 654321, CONF_GENERATION: GEN3},
        options={CONF_MAX_RUN_HOURS: hours} if hours else {},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _wait(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, minutes: float
) -> None:
    freezer.tick(timedelta(minutes=minutes))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def _set(hass: HomeAssistant, entry: MockConfigEntry, fire: FakeG3, **kw):
    fire.state.update(kw)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()


# Maximum run time -----------------------------------------------------------


async def test_turns_off_after_limit(
    hass: HomeAssistant, fake_g3: FakeG3, freezer: FrozenDateTimeFactory
) -> None:
    events = async_capture_events(hass, EVENT_AUTO_OFF)
    fake_g3.state["state"] = "heating"
    entry = await _setup(hass, hours=2)
    await _wait(hass, freezer, 119)
    assert OFF not in fake_g3.posts
    await _wait(hass, freezer, 2)
    assert fake_g3.posts == [OFF]
    assert fake_g3.state["state"] == "shutting_down"
    assert [e.data for e in events] == [
        {"entry_id": entry.entry_id, "name": "Escea 654321", "hours": 2}
    ]
    # Off now, so nothing more is sent.
    await _wait(hass, freezer, 300)
    assert fake_g3.posts == [OFF]


async def test_disabled_does_nothing(
    hass: HomeAssistant, fake_g3: FakeG3, freezer: FrozenDateTimeFactory
) -> None:
    fake_g3.state["state"] = "heating"
    await _setup(hass)
    await _wait(hass, freezer, 13 * 60)
    assert fake_g3.posts == []


async def test_restart_counts_from_startup(
    hass: HomeAssistant, fake_g3: FakeG3, freezer: FrozenDateTimeFactory
) -> None:
    """A fire already on at startup gets the full time, never less."""
    fake_g3.state["state"] = "heating"
    entry = await _setup(hass, hours=2)
    await _wait(hass, freezer, 60)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    await _wait(hass, freezer, 90)  # 2.5 h on, 1.5 h since the restart
    assert fake_g3.posts == []
    await _wait(hass, freezer, 31)
    assert fake_g3.posts == [OFF]


async def test_off_and_on_starts_again(
    hass: HomeAssistant, fake_g3: FakeG3, freezer: FrozenDateTimeFactory
) -> None:
    entry = await _setup(hass, hours=2)
    await _set(hass, entry, fake_g3, state="heating")
    await _wait(hass, freezer, 90)
    await _set(hass, entry, fake_g3, state="off")
    await _set(hass, entry, fake_g3, state="starting")
    await _wait(hass, freezer, 90)  # 3 h of running, 1.5 h since relit
    assert fake_g3.posts == []
    await _wait(hass, freezer, 31)
    assert fake_g3.posts == [OFF]


async def test_missed_poll_keeps_the_clock(
    hass: HomeAssistant, fake_g3: FakeG3, freezer: FrozenDateTimeFactory
) -> None:
    fake_g3.state["state"] = "heating"
    entry = await _setup(hass, hours=1)
    coordinator = entry.runtime_data
    with patch.object(
        coordinator.client, "async_get_status", side_effect=EsceaConnectionError("x")
    ):
        await coordinator.async_refresh()
        await hass.async_block_till_done()
    await _wait(hass, freezer, 61)
    assert fake_g3.posts == [OFF]


async def test_retries_a_failed_turn_off(
    hass: HomeAssistant, fake_g3: FakeG3, freezer: FrozenDateTimeFactory
) -> None:
    events = async_capture_events(hass, EVENT_AUTO_OFF)
    fake_g3.state["state"] = "heating"
    entry = await _setup(hass, hours=1)
    real_set = entry.runtime_data.client.async_set
    calls = 0

    async def flaky(**kwargs: bool) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise EsceaConnectionError("x")
        await real_set(**kwargs)

    with patch.object(entry.runtime_data.client, "async_set", flaky):
        await _wait(hass, freezer, 61)
        assert fake_g3.posts == []
        assert events == []
        await _wait(hass, freezer, 1)
    assert fake_g3.posts == [OFF]
    assert len(events) == 1


async def test_options_for_wifi_fire(hass: HomeAssistant, fake_g3: FakeG3) -> None:
    """Wi-Fi fires have options too, but only the maximum run time."""
    entry = await _setup(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert list(result["data_schema"].schema) == [CONF_MAX_RUN_HOURS]
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_MAX_RUN_HOURS: 4}
    )
    await hass.async_block_till_done()
    assert entry.options == {CONF_MAX_RUN_HOURS: 4}


# Fault event ----------------------------------------------------------------


async def test_fault_events(
    hass: HomeAssistant, fake_g3: FakeG3, freezer: FrozenDateTimeFactory
) -> None:
    entry = await _setup(hass)
    assert hass.states.get(FAULT).state == STATE_UNKNOWN

    await _set(hass, entry, fake_g3, state="starting")
    assert hass.states.get(FAULT).state == STATE_UNKNOWN

    await _set(hass, entry, fake_g3, state="retrying")
    state = hass.states.get(FAULT)
    assert state.attributes["event_type"] == "ignition_failed"
    assert state.attributes["state"] == "retrying"
    first = state.state

    # Still retrying: not announced twice.
    await _set(hass, entry, fake_g3, room_temp_deci_c=190)
    assert hass.states.get(FAULT).state == first

    freezer.tick(timedelta(seconds=1))  # event state is its timestamp
    await _set(hass, entry, fake_g3, state="error")
    state = hass.states.get(FAULT)
    assert state.attributes["event_type"] == "fault"
    assert state.state != first
    second = state.state

    freezer.tick(timedelta(seconds=1))  # event state is its timestamp
    await _set(hass, entry, fake_g3, state="off", errors=True)
    state = hass.states.get(FAULT)
    assert state.attributes["event_type"] == "fault"
    assert state.attributes["stored_errors"] is True
    assert state.state != second


async def test_fault_at_startup_not_announced(
    hass: HomeAssistant, fake_g3: FakeG3
) -> None:
    fake_g3.state.update(state="error", errors=True)
    await _setup(hass)
    assert hass.states.get(FAULT).state == STATE_UNKNOWN


async def test_no_fault_event_on_ethernet_fires(
    hass: HomeAssistant, loaded: MockConfigEntry
) -> None:
    assert not hass.states.async_entity_ids("event")
