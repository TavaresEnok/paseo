"""Reconcile lost send responses without issuing a second logical message."""
import json


def accepted_timeline(timeline,message_id):
    # Require provider acknowledgement, never match UUIDs mentioned in text.
    for entry in (timeline or {}).get('entries',[]):
        item=entry.get('item') or {}
        if item.get('type')=='user_message' and item.get('clientMessageId',item.get('messageId'))==message_id and entry.get('providerMessageId'):
            return True
    return False


def reconcile(core,chat,message_id):
    result=core.bridge('message-receipt',agentId=chat,messageId=message_id)
    state=(result or {}).get('state')
    if state=='completed':return 'accepted'
    if state=='missing':return 'not_received'
    if state!='pending':return 'unavailable'
    # The native receiver refuses replay of pending receipts. Do not change ID
    # to bypass this protection. An ambiguous provider outcome needs evidence.
    try:
        timeline=core.bridge('timeline',agentId=chat,options={'limit':200,'projection':'canonical'})
        if accepted_timeline(timeline,message_id):return 'accepted'
    except Exception:pass
    return 'unknown'
