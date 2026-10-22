import re
def extract(text,name):
 pattern=r'^static\s+[^;{}]*?\b'+re.escape(name)+r'\s*\([^;{}]*\)\s*\n\{'
 matches=list(re.finditer(pattern,text,re.M));assert matches,name
 m=matches[-1];start=m.start();i=text.index('{',m.start());level=0;state='code'
 while i<len(text):
  c=text[i];two=text[i:i+2]
  if state=='code':
   if two=='/*':state='comment';i+=2;continue
   if two=='//':state='line';i+=2;continue
   if c in '\"\'':state=c
   elif c=='{':level+=1
   elif c=='}':
    level-=1
    if not level:return text[start:i+1]
  elif state=='comment':
   if two=='*/':state='code';i+=2;continue
  elif state=='line':
   if c=='\n':state='code'
  elif c=='\\':i+=2;continue
  elif c==state:state='code'
  i+=1
 raise ValueError(name)
