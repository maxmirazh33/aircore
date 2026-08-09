"""Extra device features exposed as switches."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_NAME
from .device import AcState
from .entity import AcEntity


@dataclass(frozen=True, kw_only=True)
class AcSwitchDescription(SwitchEntityDescription):
    """Feature description and the state field driving it."""

    field: str
    value: Callable[[AcState], bool]


SWITCHES: tuple[AcSwitchDescription, ...] = (
    AcSwitchDescription(
        key="display",
        translation_key="display",
        field="display",
        value=lambda state: state.display,
    ),
    AcSwitchDescription(
        key="sleep",
        translation_key="sleep",
        field="sleep",
        value=lambda state: state.sleep,
    ),
    AcSwitchDescription(
        key="health",
        translation_key="health",
        field="health",
        value=lambda state: state.health,
    ),
    AcSwitchDescription(
        key="clean",
        translation_key="clean",
        field="clean",
        value=lambda state: state.clean,
    ),
    AcSwitchDescription(
        key="mildew",
        translation_key="mildew",
        field="mildew",
        value=lambda state: state.mildew,
    ),
    AcSwitchDescription(
        key="ifeel",
        translation_key="ifeel",
        field="ifeel",
        value=lambda state: state.ifeel,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    name = entry.data.get(CONF_NAME, entry.title)
    async_add_entities(
        AcSwitch(coordinator, entry.entry_id, name, description) for description in SWITCHES
    )


class AcSwitch(AcEntity, SwitchEntity):
    """A single device feature."""

    entity_description: AcSwitchDescription

    def __init__(self, coordinator, entry_id, name, description: AcSwitchDescription) -> None:
        super().__init__(coordinator, entry_id, name)
        self.entity_description = description

    @property
    def unique_id(self) -> str:
        return f"{self.coordinator.device.mac}_{self.entity_description.key}"

    @property
    def is_on(self) -> bool:
        return self.entity_description.value(self.coordinator.state)

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.async_write(**{self.entity_description.field: True})

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_write(**{self.entity_description.field: False})
