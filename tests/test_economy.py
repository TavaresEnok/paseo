import json,sqlite3,tempfile,subprocess,unittest
from pathlib import Path
from types import SimpleNamespace
from orchestrator.manager_effort import choose
from orchestrator.notifications import deliver
from orchestrator.review_brief import brief

class Economy(unittest.TestCase):
 def test_effort(self):
  self.assertEqual(choose('verifique progresso',[],[])['effort'],'medium')
  self.assertEqual(choose('Planeje a arquitetura da migração',[],[])['effort'],'high')
  task={'id':'t','state':'blocked','attempt':3,'error':'quota exhausted','spec':'{}'}
  self.assertEqual(choose('',[],[task])['effort'],'medium')
  task['error']='merge conflict';self.assertEqual(choose('',[],[task])['effort'],'high')
  task['error']='failed invariants';self.assertEqual(choose('',[],[task])['effort'],'high')
  task['state']='done';self.assertEqual(choose('',[],[task])['effort'],'medium')
 def db(self):
  db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
  db.execute('CREATE TABLE jobs(id TEXT,state TEXT,updated REAL,notified INT,supervisor_id TEXT)')
  return db
 def test_batch_retry_and_priority(self):
  db=self.db();sent=[];clock=[1];fail=[True]
  def send(*a,**kw):
   sent.append(kw)
   if fail[0]:raise OSError('transport')
  c=SimpleNamespace(now=lambda:clock[0],report=lambda j:None,bridge=send,event=lambda *a:None)
  db.executemany('INSERT INTO jobs VALUES(?,?,?,0,?)',[('a','done',1,'chat'),('b','done',1,'chat'),('c','blocked',1,'other')])
  rows=lambda:db.execute('SELECT * FROM jobs WHERE notified=0').fetchall()
  deliver(db,rows(),c);self.assertEqual(len(sent),1);self.assertEqual(sent[0]['agentId'],'other')
  fail[0]=False;deliver(db,rows(),c);self.assertEqual(sent[0]['options']['messageId'],sent[1]['options']['messageId'])
  clock[0]=22;deliver(db,rows(),c);self.assertEqual(len(sent),3);self.assertIn('a: done',sent[-1]['prompt']);self.assertIn('b: done',sent[-1]['prompt'])
  self.assertEqual(sent[-1]['options']['activeTurnBehavior'],'steer');deliver(db,rows(),c);self.assertEqual(len(sent),3)
 def test_paused_retry_not_sent(self):
  db=self.db();db.execute("INSERT INTO jobs VALUES('a','blocked',1,0,'chat')")
  c=SimpleNamespace(now=lambda:1,report=lambda j:None,bridge=lambda *a,**k:(_ for _ in ()).throw(OSError()),event=lambda *a:None)
  deliver(db,db.execute('SELECT * FROM jobs').fetchall(),c)
  db.execute("UPDATE jobs SET state='paused',updated=2")
  c.bridge=lambda *a,**k:self.fail('paused notification sent')
  deliver(db,[],c)
 def test_diff_and_untracked(self):
  with tempfile.TemporaryDirectory() as d:
   def git(*a):subprocess.run(['git','-C',d,*a],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
   git('init');Path(d,'a').write_text('before\n');git('add','a');git('-c','user.name=test','-c','user.email=test@example.invalid','commit','-m','base')
   Path(d,'a').write_text('after\n');Path(d,'new').write_text('untracked')
   Path(d,'.paseo-result.json').write_text(json.dumps({'status':'completed','tests':[{'command':'check','exit_code':0}]}))
   value=brief(d);self.assertIn('+after',value);self.assertIn('?? new',value);self.assertIn('check',value);self.assertIn('NÃO aparecem',value)
   self.assertIn('Recorte',brief(d,5))

if __name__=='__main__':unittest.main()
