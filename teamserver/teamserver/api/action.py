"""
    This module contains all 'Action' API functions.
"""
from uuid import uuid4

import time

from ..utils import get_context, success_response, handle_exceptions, log
from ..models import Action, Target, Session
from ..config import SESSION_STATUSES
from ..exceptions import CannotBindAction

@handle_exceptions
def create_action(params, commit=True):
    """
    ### Overview
    This API function creates a new action object in the database.

    ### Parameters
    target_name (unique):           The name of the target to perform the action on. <str>
    action_string:                  The action string that will be parsed into an action. <str>
    bound_session_id (optional):    This will restrict the action to only be retrieved
                                        by a specific session. <str>
    action_id (optional, unique):   Specify a human readable action_id. <str>
    quick (optional):               Only send to the target's fastest session. <bool>
                                        Default: False. This overrides bound_session_id
    """
    username = 'No owner'

    try:
        user, _, _ = get_context(params)
        if user:
            username = user.username
    except KeyError:
        pass

    target_name = params['target_name']
    action_string = params['action_string']
    bound_session_id = params.get('bound_session_id')

    # Ensure Target exists
    target = Target.get_by_name(target_name)
    if not target:
        raise CannotBindAction(target_name)

    parsed_action = Action.parse_action_string(action_string)

    if params.get('quick', False):
        bound_session = min(
            filter(
                lambda x: x.status == SESSION_STATUSES.get('active', 'active'),
                target.sessions),
            key=lambda x: x.interval
        )

        if bound_session and isinstance(bound_session, Session):
            bound_session_id = bound_session.session_id

    action = Action(
        action_id=params.get('action_id', str(uuid4())),
        target_name=target_name,
        action_string=action_string,
        action_type=parsed_action['action_type'],
        bound_session_id=bound_session_id,
        queue_time=time.time(),
        owner=username,
    )

    action.update_fields(parsed_action)

    if commit:
        action.save(force_insert=True)
        log(
            'INFO',
            'Action Created (action: {}) on (target: {})'.format(action_string, target_name))
    else:
        return action

    return success_response(action_id=action.action_id)

@handle_exceptions
def get_action(params):
    """
    ### Overview
    Retrieves an action from the database based on action_id.

    ### Parameters
    action_id: The action_id of the action to query for. <str>
    """
    action = Action.get_by_id(params['action_id'])

    return success_response(action=action.document)

@handle_exceptions
def cancel_action(params):
    """
    ### Overview
    Cancels an action if it has not yet been sent.
    This will prevent sessions from retrieving it.

    ### Parameters
    action_id: The action_id of the action to cancel. <str>
    """
    action = Action.get_by_id(params['action_id'])
    action.cancel()

    return success_response()

@handle_exceptions
def list_actions(params): #pylint: disable=unused-argument
    """
    ### Overview
    This API function will return a list of action documents.
    Filters are available for added efficiency.

    ### Parameters
    owner (optional):       Only display actions owned by this user. <str>
    target_name (optional): Only display actions for given target. <str>
    limit (optional):       Optionally limit how many values may be returned. <int>
    offset (optional):      The position to start listing from. <int>
    """
    actions = Action.list_actions(
        owner=params.get('owner'),
        target_name=params.get('target_name'),
        limit=params.get('limit'),
        offset=params.get('offset', 0))

    return success_response(actions={action.action_id: action.document for action in actions})

@handle_exceptions
def duplicate_action(params):
    """
    ### Overview
    This API function is used to queue an identical action to the given action_id.

    ### Parameters
    action_id: The unique identifier of the action to clone. <str>
    """
    action = Action.get_by_id(params['action_id'])

    local_params = {
        'arsenal_auth_object': params['arsenal_auth_object'],
        'target_name': action.target_name,
        'action_string': action.action_string,
    }

    if action.bound_session_id:
        local_params['bound_session_id'] = action.bound_session_id

    return create_action(local_params)
