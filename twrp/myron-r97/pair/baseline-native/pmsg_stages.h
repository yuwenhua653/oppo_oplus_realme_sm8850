/* R40 optional normal-boot breadcrumbs. No block device is opened; no event()
 * calls or report_error writes are allowed here. Failure disables only this
 * sink. Recovery never initializes it, preserving prior-boot pstore content.
 * Raw R36_PROBE lines are bracketed by independently identifiable markers.
 */
#define PMSG_EARLY_MAX (16U * 1024U)
#define PMSG_TOTAL_MAX (128U * 1024U)
#define PMSG_END_RESERVE 512U
#define PMSG_WRITE_TRIES 32U
#define PMSG_NODE BASE "/dev/r40-pmsg0"
enum { PMSG_BUFFERING, PMSG_ACTIVE, PMSG_DISABLED, PMSG_FINISHED };
struct pmsg_state {
 int state,fd;
 size_t early_used,total;
 unsigned early_dropped;
 char early[PMSG_EARLY_MAX];
};
static struct pmsg_state pmsg={.fd=-1};
struct pmsg_calls {
 int (*read_text)(const char*,char*,size_t);
 int (*lstat_fn)(const char*,struct stat*);
 int (*mknod_fn)(const char*,mode_t,dev_t);
 int (*open_fn)(const char*,int);
 int (*fstat_fn)(int,struct stat*);
 ssize_t (*write_fn)(int,const void*,size_t);
 int (*close_fn)(int);
};
/* Separate from read_small(): its input-truncated branch logs a main event.
 * Optional discovery must never alter the primary report or failure state. */
static int pmsg_read_text(const char *path,char *out,size_t cap){
 int fd=open(path,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);if(fd<0)return -1;
 size_t used=0;int result=-1;
 while(used<cap){
  ssize_t n=read(fd,out+used,cap-used);
  if(n<0)break;
  if(!n){out[used]=0;result=0;break;}
  used+=(size_t)n;
 }
 if(close(fd))result=-1;
 return result;
}
static struct pmsg_calls pmsg_call={pmsg_read_text,lstat,mknod,real_open,fstat,write,close};
static void pmsg_close(int state){
 int fd=pmsg.fd;pmsg.fd=-1;pmsg.state=state;
 if(fd>=0)(void)pmsg_call.close_fn(fd); /* Never retry close. */
}
static int pmsg_write_bytes(const char *data,size_t n,size_t limit){
 size_t off=0;unsigned tries=0;
 if(pmsg.state!=PMSG_ACTIVE)return -1;
 if(n>limit||pmsg.total>limit-n)return -1;
 while(off<n&&tries++<PMSG_WRITE_TRIES){
  ssize_t written=pmsg_call.write_fn(pmsg.fd,data+off,n-off);
  if(written<0&&errno==EINTR)continue;
  if(written<=0||(size_t)written>n-off){pmsg_close(PMSG_DISABLED);return -1;}
  off+=(size_t)written;pmsg.total+=(size_t)written;
 }
 if(off!=n){pmsg_close(PMSG_DISABLED);return -1;}
 return 0;
}
static int pmsg_marker(const char *name,const char *detail,size_t limit){
 char line[PMSG_END_RESERVE];
 int n=snprintf(line,sizeof(line),"R40_PMSG build_id=%s boot_id=%s seq=%u event=%s%s%s\n",
                R36_BUILD_ID,boot_id,sequence,name,*detail?" ":"",detail);
 if(n<0||(size_t)n>=sizeof(line)){pmsg_close(PMSG_DISABLED);return -1;}
 return pmsg_write_bytes(line,(size_t)n,limit);
}
static void pmsg_finish(const char *reason){
 int saved=errno;
 if(pmsg.state==PMSG_ACTIVE){
  char detail[160];snprintf(detail,sizeof(detail),"reason=%s bytes=%zu",reason,pmsg.total);
  (void)pmsg_marker("end",detail,PMSG_TOTAL_MAX);
  pmsg_close(PMSG_FINISHED);
 }
 errno=saved;
}
static void pmsg_event(const char *line,size_t n){
 int saved=errno;
 if(recovery_mode){errno=saved;return;}
 if(pmsg.state==PMSG_BUFFERING){
  if(n<=PMSG_EARLY_MAX-pmsg.early_used){memcpy(pmsg.early+pmsg.early_used,line,n);pmsg.early_used+=n;}
  else if(pmsg.early_dropped!=UINT32_MAX)pmsg.early_dropped++;
 }else if(pmsg.state==PMSG_ACTIVE){
  if(n>PMSG_TOTAL_MAX-PMSG_END_RESERVE||pmsg.total>PMSG_TOTAL_MAX-PMSG_END_RESERVE-n)pmsg_finish("budget");
  else (void)pmsg_write_bytes(line,n,PMSG_TOTAL_MAX-PMSG_END_RESERVE);
 }
 errno=saved;
}
static int pmsg_device_number(char *sysdev,char *devices,dev_t *out){
 unsigned wanted_major,wanted_minor;char extra;
 if(sscanf(sysdev,"%u:%u %c",&wanted_major,&wanted_minor,&extra)!=2||
    !wanted_major||wanted_major>0xfff||wanted_minor>0xfffff)return -1;
 int chars=0;unsigned matches=0;char *save=NULL;
 for(char *line=strtok_r(devices,"\n",&save);line;line=strtok_r(NULL,"\n",&save)){
  if(!strcmp(line,"Character devices:")){chars=1;continue;}
  if(!strcmp(line,"Block devices:")){chars=0;continue;}
  unsigned num;char name[64];
  if(chars&&sscanf(line," %u %63s %c",&num,name,&extra)==2&&!strcmp(name,"pmsg")){
   if(num!=wanted_major||++matches!=1)return -1;
  }
 }
 if(matches!=1)return -1;
 *out=makedev(wanted_major,wanted_minor);return 0;
}
static int pmsg_node_ok(const struct stat *st,dev_t rootdev,dev_t device){
 return S_ISCHR(st->st_mode)&&!st->st_uid&&!st->st_gid&&
        (st->st_mode&07777)==0600&&st->st_dev==rootdev&&st->st_rdev==device;
}
static void pmsg_start(int normal,dev_t rootdev){
 int saved=errno,fd=-1;char sysdev[80],devices[16384],detail[128];struct stat st;dev_t device;
 if(!normal||recovery_mode||pmsg.state!=PMSG_BUFFERING){errno=saved;return;}
 pmsg.state=PMSG_DISABLED;
 if(pmsg_call.read_text(BASE"/sys/class/pmsg/pmsg0/dev",sysdev,sizeof(sysdev))||
    pmsg_call.read_text(BASE"/proc/devices",devices,sizeof(devices))||
    pmsg_device_number(sysdev,devices,&device))goto done;
 if(pmsg_call.lstat_fn(BASE"/dev",&st)||!S_ISDIR(st.st_mode)||st.st_uid||st.st_gid||
    (st.st_mode&022)||st.st_dev!=rootdev)goto done;
 if(pmsg_call.mknod_fn(PMSG_NODE,S_IFCHR|0600,device)||
    pmsg_call.lstat_fn(PMSG_NODE,&st)||!pmsg_node_ok(&st,rootdev,device))goto done;
 fd=pmsg_call.open_fn(PMSG_NODE,O_WRONLY|O_NONBLOCK|O_CLOEXEC|O_NOFOLLOW);
 if(fd<0||pmsg_call.fstat_fn(fd,&st)||!pmsg_node_ok(&st,rootdev,device))goto done;
 pmsg.fd=fd;fd=-1;pmsg.state=PMSG_ACTIVE;
 snprintf(detail,sizeof(detail),"mode=normal_candidate early_bytes=%zu early_dropped=%u",pmsg.early_used,pmsg.early_dropped);
 if(pmsg_marker("begin",detail,PMSG_TOTAL_MAX-PMSG_END_RESERVE))goto done;
 if(pmsg_write_bytes(pmsg.early,pmsg.early_used,PMSG_TOTAL_MAX-PMSG_END_RESERVE))goto done;
 snprintf(detail,sizeof(detail),"early_bytes=%zu early_dropped=%u",pmsg.early_used,pmsg.early_dropped);
 (void)pmsg_marker("replay_complete",detail,PMSG_TOTAL_MAX-PMSG_END_RESERVE);
done:
 if(fd>=0)(void)pmsg_call.close_fn(fd);
 errno=saved;
}
static void pmsg_pre_exec(void){
 int saved=errno;
 if(!recovery_mode&&pmsg.state==PMSG_ACTIVE){
  const char *detail="target=/init exec_success_verified=0";
  if(pmsg.total>PMSG_TOTAL_MAX-PMSG_END_RESERVE-512U)pmsg_finish("budget");
  else (void)pmsg_marker("pre_exec",detail,PMSG_TOTAL_MAX-PMSG_END_RESERVE);
 }
 errno=saved;
}
