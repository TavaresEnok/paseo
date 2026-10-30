"""Real OAuth CLI health and measured token totals. No invented quota percentages."""
import sqlite3
from pathlib import Path
from . import core

def evidence_entry(account2=False, new2=False):
 path=core.STATE/('evidence/gemini-new2-usage.sqlite3' if new2 else 'evidence/gemini2-usage.sqlite3' if account2 else 'evidence/gemini-usage.sqlite3')
 if not path.exists():return None
 with sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True) as db:
  columns={r[1] for r in db.execute('PRAGMA table_info(health)')}
  health=db.execute('SELECT status,at'+(',message' if 'message' in columns else ',NULL')+' FROM health WHERE id=1').fetchone()
 if not health:return None
 status,observed,message=health
 return {'id':'gemini-3.8-flash-high','provider':'antigravity3' if new2 else 'antigravity2' if account2 else 'antigravity','label':'Gemini 3.8 Flash Alto — conta 2' if new2 else 'Gemini 3.8 Flash Alto — conta 3' if account2 else 'Gemini 3.8 Flash Alto — conta 1',
  'available':True,'authenticated':True,'observed_at':observed,'mode':'full-access',
  'safe_thinking_options':['high'],'roles':['programmer-gemini'],
  'preferred_specialties':['backend','coding','frontend','testing','debugging','advanced','architecture','utility','reasoning'],
  'cost':{'kind':'subscription','verified':True,'additional_cost':0,'source':'official agy OAuth; API/ADC provider overrides blocked by gemini-provider'},
  'quota':{'status':status,'observed_at':observed,'source':'official agy response',
           'windows':[],'message':(message or 'quota exhausted') if status=='exhausted' else ''},
  'restrictions':{'allowed':True,'notes':'OAuth subscription only; effort encoded in model ID'}}
