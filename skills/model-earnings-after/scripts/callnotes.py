"""The Call Notes tab: one column per quarter (newest at B), topic rows, near-verbatim points with file:line notes.
For now only the topic list (context.py hands it to the agent); read / merge / lay_out come with the tab itself."""

TAB = "Call Notes"
FIXED_TOP = ["Guidance (near-term)", "Long-term targets"]
FIXED_BOTTOM = ["Margins and costs", "Capital allocation"] + [f"Q&A theme {i}" for i in range(1, 6)] + \
    ["Tone", "Read-throughs mentioned"]


def topics(drivers):
    """The tab's topic rows in order: the fixed top rows, one 'Driver: <name>' per forecast-plan driver, the rest."""
    return FIXED_TOP + [f"Driver: {d}" for d in drivers] + FIXED_BOTTOM
