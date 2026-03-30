"""
Konstanty pro akce agentů – sdílené napříč komponentami.
"""

ACTION_CONTINUE = 0
ACTION_FETCH_MORE = 1
ACTION_DEEP_DIVE = 2
ACTION_BRANCH = 3
ACTION_YIELD = 4

ACTION_NAMES = {
    ACTION_CONTINUE: 'continue',
    ACTION_FETCH_MORE: 'fetch_more',
    ACTION_DEEP_DIVE: 'deep_dive',
    ACTION_BRANCH: 'branch',
    ACTION_YIELD: 'yield'
}

ACTION_DIM = 5
