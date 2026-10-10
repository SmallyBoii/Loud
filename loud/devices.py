"""Which playback device is the headphones and which is Loud's silent input."""

VIRTUAL_HINTS = ("cable", "vb-audio", "voicemeeter", "virtual")
CABLE_URL = "https://vb-audio.com/Cable/"


def is_virtual(name):
    """True for virtual audio devices (VB-Cable and friends), which are silent: no speaker behind them."""
    lowered = name.lower()
    return any(hint in lowered for hint in VIRTUAL_HINTS)


def choose(devices, default_id, saved_output=None, saved_source=None):
    """Pick (output_id, source_id) from [(id, name)].

    Output is the saved choice, else the Windows default, never a virtual device if a real one exists.
    Source is the saved choice, else a virtual device, else any other device (a monitor's audio).
    source_id is None when the PC has no second device to listen on."""
    ids = [ident for ident, _ in devices]
    names = dict(devices)
    real = [i for i in ids if not is_virtual(names[i])]

    output = saved_output if saved_output in ids else None
    if output is None:
        output = default_id if default_id in real else (real[0] if real else default_id)

    source = saved_source if saved_source in ids and saved_source != output else None
    if source is None:
        others = [i for i in ids if i != output]
        source = next((i for i in others if is_virtual(names[i])), others[0] if others else None)
    return output, source
