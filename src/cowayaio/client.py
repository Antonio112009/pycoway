"""Python API for Coway IoCare Purifiers."""

from cowayaio.devices.control import CowayControlClient


class CowayClient(CowayControlClient):
    """Coway IoCare API client.

    Inheritance chain:
        CowayHttpClient → CowayAuthClient → CowayDataClient
        → CowayMaintenanceClient → CowayControlClient → CowayClient
    """
