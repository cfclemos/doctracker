"""Integrations with the agents that use doctracker (Claude Code, OpenCode), and the texts they share."""

SERVER_DOWN = ("doctracker is not running at {url}, so its plans, guidelines and memory are not available. "
               "Ask the user whether to start it (`doctracker start` in the project) or to work with local "
               "memory in this session.")
"""Given at the start of a session when the server does not answer: the user decides."""

RECORD_THE_PLAN = ("Plans are kept in doctracker's Planner: once the user approves this plan, record it there "
                   "(create_plan, or add_feature / add_task to an open plan) with its requirements, the decisions "
                   "taken with the user and the criteria of each task.")
"""Given when plan mode ends."""
