/* Create a new namespace-list entry after the DLKM parents. MS_MOVE alone
 * keeps the original entry's earlier order, which the installed init's
 * SwitchRoot uses while selecting parent mounts. No recursive bind is used. */
static int (*report_fstat)(int,struct stat*)=fstat;
static int (*read_mount_text)(const char*,char*,size_t)=read_small;

static int open_report_log(const char *root){
 char path[160];struct stat st;
 snprintf(path,sizeof(path),"%s/probe.log",root);
 int fd=call.open_fn(path,O_WRONLY|O_APPEND|O_CLOEXEC|O_NOFOLLOW);
 if(fd<0)return -1;
 if(report_fstat(fd,&st)||!S_ISREG(st.st_mode)||st.st_uid||st.st_gid||
    (st.st_mode&0777)!=0644||st.st_dev!=report_identity.st_dev||st.st_ino!=report_identity.st_ino){
  int e=errno?errno:EINVAL;close_tracked(&fd,"rejected-report-log");errno=e;return -1;
 }
 return fd;
}
static int switch_report_log(const char *root){
 int replacement=open_report_log(root);if(replacement<0)return -1;
 int old=reportfd;reportfd=replacement;
 /* Keep the verified replacement as the active logger even if old close
  * fails. Never retry close: Linux may already have released that fd. */
 if(close_tracked(&old,"report-old-mount"))return -1;
 event("report_fd_reopened",0,"path=%s/probe.log",root);
 return report_error?-1:0;
}
struct report_mount_row {unsigned line,id,parent;dev_t dev;};
static int report_path_kind(const char *path){
 if(!strcmp(path,targets[0]))return 0;
 if(!strcmp(path,targets[1]))return 1;
 if(!strcmp(path,REPORT_HELD))return 2;
 if(!strcmp(path,REPORT_ROOT))return 3;
 return -1;
}
static int parse_report_order(char *text,int mountinfo,struct state *s){
 struct report_mount_row row[4]={{0}};unsigned count[4]={0},line=0;char *save=NULL;
 for(char *p=strtok_r(text,"\n",&save);p;p=strtok_r(NULL,"\n",&save)){
  char *ts=NULL,*word[6];line++;
  for(unsigned i=0;i<6;i++){word[i]=strtok_r(i?NULL:p," ", &ts);if(!word[i])return mismatch("mount-table-malformed");}
  const char *path=mountinfo?word[4]:word[1];int kind=report_path_kind(path);
  if(kind<0)continue;
  if(++count[kind]!=1)return mismatch("report-order-duplicate");
  row[kind].line=line;
  if(mountinfo){
   char tail;unsigned id,parent,a,b;
   if(sscanf(word[0],"%u%c",&id,&tail)!=1||sscanf(word[1],"%u%c",&parent,&tail)!=1||
      sscanf(word[2],"%u:%u%c",&a,&b,&tail)!=2||!id||!parent||a>0xfff||b>0xfffff)return mismatch("mountinfo-identity");
   row[kind].id=id;row[kind].parent=parent;row[kind].dev=makedev(a,b);
   char *sep;do{sep=strtok_r(NULL," ",&ts);}while(sep&&strcmp(sep,"-"));
   char *fs=sep?strtok_r(NULL," ",&ts):NULL;
   if(!fs||strcmp(fs,kind==2||kind==3?"tmpfs":"ext4"))return mismatch("mountinfo-filesystem");
  }else if(strcmp(word[2],kind==2||kind==3?"tmpfs":"ext4"))return mismatch("mounts-filesystem");
 }
 if(count[3]||count[0]!=1||count[1]!=1||count[2]!=1)return mismatch("report-order-mount-set");
 if(row[2].line<=row[0].line||row[2].line<=row[1].line)return mismatch("report-before-parent");
 if(mountinfo&&(row[2].parent!=row[1].id||row[0].dev!=s->dev[0]||row[1].dev!=s->dev[1]||row[2].dev!=report_dev))return mismatch("report-mount-parent-identity");
 event("report_order_verified",0,"table=%s system_line=%u vendor_line=%u report_line=%u report_parent=%u vendor_mount_id=%u original_absent=1",mountinfo?"mountinfo":"mounts",row[0].line,row[1].line,row[2].line,row[2].parent,row[1].id);
 return report_error?-1:0;
}
static int verify_report_order(struct state *s){
 char text[65536];s->report_order_verified=0;
 if(s->report_original||!s->report_moved||!s->mounted[0]||!s->mounted[1])return mismatch("report-order-state");
 if(read_mount_text(BASE"/proc/self/mountinfo",text,sizeof(text))||parse_report_order(text,1,s))return -1;
 if(read_mount_text(BASE"/proc/self/mounts",text,sizeof(text))||parse_report_order(text,0,s))return -1;
 s->report_order_verified=1;return 0;
}
static int report_anchor(const char *path,dev_t expected){
 struct stat st;if(empty_path(path,expected)||call.lstat_fn(path,&st))return -1;
 return (st.st_mode&0777)==0755?0:mismatch("report-anchor-mode");
}
static int reanchor_report(struct state *s){
 phase("report-reanchor");
 if(!s->report_mounted||!s->report_original||s->report_moved||!s->mounted[0]||!s->mounted[1])return mismatch("report-reanchor-state");
 if(verify_report(REPORT_ROOT)||report_anchor(REPORT_HELD,s->dev[1]))return -1;
 if(call.mount_fn(REPORT_ROOT,REPORT_HELD,NULL,MS_BIND,NULL))return -1;
 s->report_moved=1;
 if(verify_report(REPORT_HELD)||switch_report_log(REPORT_HELD))return -1;
 /* The log fd now names the new bind. Leaving it on the original mount
  * would make this unmount busy despite both paths naming the same inode. */
 if(call.umount_fn(REPORT_ROOT,0))return -1;
 s->report_original=0;
 if(root_restored(s,REPORT_ROOT)||verify_report(REPORT_HELD)||verify_report_order(s))return -1;
 event("report_reanchored",0,"from=%s to=%s same_tmpfs=1 same_log_inode=1 original_absent=1",REPORT_ROOT,REPORT_HELD);
 return report_error?-1:0;
}
static int return_report(struct state *s){
 phase("report-return");s->report_order_verified=0;
 if(!s->report_mounted||!s->report_moved)return mismatch("report-return-state");
 if(s->report_original){
  /* Bind exists, old mount was not removed. Move the fd back before
   * unmounting the duplicate; never stack a mount over the original. */
  if(verify_report(REPORT_ROOT)||switch_report_log(REPORT_ROOT))return -1;
  if(call.umount_fn(REPORT_HELD,0))return -1;
  s->report_moved=0;
 }else{
  if(report_anchor(REPORT_ROOT,s->rootdev))return -1;
  if(call.mount_fn(REPORT_HELD,REPORT_ROOT,NULL,MS_MOVE,NULL))return -1;
  s->report_moved=0;s->report_original=1;
 }
 if(verify_report(REPORT_ROOT))return -1;
 event("report_returned",0,"from=%s to=%s",REPORT_HELD,REPORT_ROOT);return 0;
}
