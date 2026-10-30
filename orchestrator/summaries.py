"""Bound supervisor context while retaining complete evidence on disk."""
from collections import Counter

def compact_report(report):
    job=report['job'];tasks=[]
    ordered=sorted(job['tasks'],key=lambda task:task['state']=='done')
    for task in ordered[:50]:
        result=task.get('result') or {};selection=task.get('selection') or {}
        tests=[]
        for check in result.get('integration_tests',result.get('tests',[])):
            entry={key:check.get(key) for key in ['command','exit_code','seconds']}
            if check.get('exit_code'):entry['error']=(check.get('stderr') or check.get('stdout') or '')[-1600:]
            tests.append(entry)
        tasks.append({'id':task['id'],'task':task['task_key'],'state':task['state'],'attempt':task['attempt'],
            'model':task['model'],'review_model':task['review_model'],'agent_id':task['agent_id'],
            'branch':task['branch'],'commit':task['commit_sha'],
            'selection_reason':selection.get('preference_reason'),
            'summary':(result.get('implementation') or {}).get('summary'),
            'review':result.get('review'),'tests':tests,'error':(task.get('error') or '')[-1600:]})
    important={'correction_requested','task_blocked','job_blocked','intentional_test_defect_injected','supervisor_failover','integration_blocked'}
    decisions=[{'kind':e['kind'],'data':e['data']} for e in report['events'] if e['kind'] in important][-10:]
    return {'id':job['id'],'objective':job['objective'],'state':job['state'],'branch':job['branch'],
            'plan_hash':job['plan_hash'],'tasks':tasks,'omitted_tasks':max(0,len(job['tasks'])-len(tasks)),
            'task_counts':dict(Counter(t['state'] for t in job['tasks'])),
            'event_counts':dict(Counter(e['kind'] for e in report['events'])),
            'decisions':decisions,'generated_at':report['generated_at'],
            'full_evidence':'/home/enok/srv_projetos/orchestration/reports/'+job['id']+'.json'}

def overview(jobs):
    return [{'id':job['id'],'objective':job['objective'],'state':job['state'],'branch':job['branch'],
             'supervisor_id':job['supervisor_id'],'task_counts':dict(Counter(t['state'] for t in job['tasks']))} for job in jobs]
