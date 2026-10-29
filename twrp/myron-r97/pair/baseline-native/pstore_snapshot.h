/* R38 best-effort Recovery evidence capture. Included after SHA and event().
 * Never unlinks a pstore record, loads a module, or opens a block device.
 * Bounds cover actual source reads, not unreliable st_size (which may be zero).
 */
#define PS_FILE_MAX (4ULL * 1024 * 1024)
#define PS_TOTAL_MAX (6ULL * 1024 * 1024)
#define PS_FILES_MAX 16U
#define PS_MOUNT_FLAGS (MS_RDONLY|MS_NOSUID|MS_NODEV|MS_NOEXEC)

struct ps_calls {
 ssize_t (*read_fn)(int,void*,size_t);
 ssize_t (*write_fn)(int,const void*,size_t);
 int (*fstat_fn)(int,struct stat*);
 int (*fstatfs_fn)(int,struct statfs*);
 int (*close_fn)(int);
};
static struct ps_calls ps_call={read,write,fstat,fstatfs,close};
struct ps_result {
 const char *status;
 int error;
 unsigned files, entries;
 uint64_t read_bytes, bytes;
 char manifest[16384];
 size_t used;
};
static void ps_problem(struct ps_result *r,int e){
 r->status="partial";
 if(!r->error)r->error=e?e:EIO;
}
static int ps_line(struct ps_result*r,const char *fmt,...){
 va_list ap;va_start(ap,fmt);
 int n=vsnprintf(r->manifest+r->used,sizeof(r->manifest)-r->used,fmt,ap);
 va_end(ap);
 if(n<0||(size_t)n>=sizeof(r->manifest)-r->used){ps_problem(r,EOVERFLOW);return -1;}
 r->used+=(size_t)n;return 0;
}
static int ps_name(const char*n){
 size_t z=strlen(n);
 if(!z||z>128||!strcmp(n,"manifest.tsv"))return 0;
 for(size_t i=0;i<z;i++){
  unsigned c=(unsigned char)n[i];
  if((c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9'))continue;
  if(i&&(c=='_'||c=='-'||c=='.'))continue;
  return 0;
 }
 return 1;
}
static int ps_dir(int fd,dev_t dev,mode_t mode){
 struct stat st;
 if(ps_call.fstat_fn(fd,&st))return -1;
 if(!S_ISDIR(st.st_mode)||st.st_uid||st.st_gid||st.st_dev!=dev||(st.st_mode&0777)!=mode){errno=EINVAL;return -1;}
 return 0;
}
static int ps_write(int fd,const void *data,size_t n){
 const unsigned char *p=data;
 while(n){
  ssize_t w=ps_call.write_fn(fd,p,n);
  if(w<0&&errno==EINTR)continue;
  if(w<=0){if(!w)errno=EIO;return -1;}
  p+=w;n-=(size_t)w;
 }
 return 0;
}
static void ps_file(int srcdir,int outdir,dev_t source_dev,const char*name,struct ps_result*r){
 char namehex[511],hex[65]="-";
 size_t len=strlen(name);
 for(size_t i=0;i<len;i++)snprintf(namehex+i*2,3,"%02x",(unsigned char)name[i]);
 namehex[len*2]=0;
 const char *saved="-",*status="complete";
 int in=-1,out=-1,e=0;
 long long stat_size=-1;
 uint64_t nr=0,nw=0;
 struct stat st;struct sha hash;sha_init(&hash);
 if(!ps_name(name)){status="rejected_name";e=EINVAL;goto done;}
 in=openat(srcdir,name,O_RDONLY|O_NONBLOCK|O_NOFOLLOW|O_CLOEXEC);
 if(in<0){status="open_error";e=errno;goto done;}
 if(ps_call.fstat_fn(in,&st)){status="stat_error";e=errno;goto done;}
 stat_size=st.st_size;
 if(!S_ISREG(st.st_mode)||st.st_dev!=source_dev||st.st_size<0){status="rejected_type";e=EINVAL;goto done;}
 out=openat(outdir,name,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0644);
 if(out<0){status="output_error";e=errno;goto done;}
 saved=name;r->files++;
 if(fchmod(out,0644)||ps_call.fstat_fn(out,&st)||!S_ISREG(st.st_mode)||st.st_uid||st.st_gid||st.st_dev!=report_dev||(st.st_mode&0777)!=0644){status="output_error";e=errno?errno:EINVAL;goto done;}
 for(;;){
  unsigned char buffer[65536];
  uint64_t left=PS_FILE_MAX-nr,total_left=PS_TOTAL_MAX-r->read_bytes;
  if(!left){status="partial_file_limit";e=EFBIG;break;}
  if(!total_left){status="partial_total_limit";e=ENOSPC;break;}
  size_t want=sizeof(buffer);
  if(left<want)want=(size_t)left;
  if(total_left<want)want=(size_t)total_left;
  ssize_t n=ps_call.read_fn(in,buffer,want);
  if(n<0&&errno==EINTR)continue;
  if(n<0){status="partial_read_error";e=errno;break;}
  if(!n){
   if(stat_size>0&&nr!=(uint64_t)stat_size){status="partial_size_mismatch";e=ESTALE;}
   break;
  }
  nr+=(uint64_t)n;r->read_bytes+=(uint64_t)n;
  size_t off=0;
  while(off<(size_t)n){
   ssize_t w=ps_call.write_fn(out,buffer+off,(size_t)n-off);
   if(w<0&&errno==EINTR)continue;
   if(w<=0){status="partial_write_error";e=w<0?errno:EIO;break;}
   sha_add(&hash,buffer+off,(size_t)w);
   off+=(size_t)w;nw+=(uint64_t)w;r->bytes+=(uint64_t)w;
  }
  if(e)break;
 }
done:
 if(in>=0&&ps_call.close_fn(in)&&!e){e=errno?errno:EIO;status="partial_close_error";}
 if(out>=0&&ps_call.close_fn(out)&&!e){e=errno?errno:EIO;status="partial_close_error";}
 if(strcmp(saved,"-"))sha_end(&hash,hex);
 if(e)ps_problem(r,e);
 (void)ps_line(r,"%s\t%s\t%s\t%lld\t%llu\t%llu\t%s\t%d\n",namehex,saved,status,stat_size,(unsigned long long)nr,(unsigned long long)nw,hex,e);
}
static void prior_pstore_snapshot_at(const char *root){
 /* Snapshot observability must not introduce a fatal report error. Preserve
  * any report error that existed before this optional operation, unchanged. */
 int old_report_error=report_error,old_errno=errno;
 const char *old_stage=stage;stage="prior-pstore-snapshot";
 struct ps_result r={.status="unavailable"};
 int rootfd=-1,outdir=-1,manifestfd=-1,sourcefd=-1,mounted=0;
 DIR *directory=NULL;
 const char *unmount_status="not_mounted";
 char mountpath[256];struct statfs sf;struct stat st;
 event("prior_pstore_snapshot_begin",0,"scope=prior-pstore origin_boot_id=unknown max_files=%u max_file_bytes=%llu max_total_bytes=%llu",PS_FILES_MAX,(unsigned long long)PS_FILE_MAX,(unsigned long long)PS_TOTAL_MAX);
 (void)ps_line(&r,"#schema\tR38_PRIOR_PSTORE_V1\n#build_id\t%s\n#current_boot_id\t%s\n#origin_boot_id\tunknown\nsource_name_hex\tsaved_name\tstatus\tstat_size\tread_bytes\tbytes\tsha256\terrno\n",R36_BUILD_ID,boot_id);
 int n=snprintf(mountpath,sizeof(mountpath),"%s/.pstore-mount",root);
 if(n<0||(size_t)n>=sizeof(mountpath)){r.error=ENAMETOOLONG;goto done;}
 rootfd=open(root,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
 if(rootfd<0||ps_dir(rootfd,report_dev,0755)||ps_call.fstatfs_fn(rootfd,&sf)){r.error=errno?errno:EIO;goto done;}
 if(sf.f_type!=TMPFS_MAGIC){r.error=EINVAL;goto done;}
 if(mkdirat(rootfd,"prior-pstore",0755)){r.error=errno;goto done;}
 outdir=openat(rootfd,"prior-pstore",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
 if(outdir<0||fchmod(outdir,0755)||ps_dir(outdir,report_dev,0755)){r.error=errno?errno:EIO;goto done;}
 manifestfd=openat(outdir,"manifest.tsv",O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0644);
 if(manifestfd<0||fchmod(manifestfd,0644)){r.error=errno?errno:EIO;goto done;}
 if(mkdirat(rootfd,".pstore-mount",0700)){r.error=errno;goto done;}
 if(call.mount_fn("pstore",mountpath,"pstore",PS_MOUNT_FLAGS,NULL)){r.error=errno;goto done;}
 mounted=1;unmount_status="residual";
 sourcefd=openat(rootfd,".pstore-mount",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
 if(sourcefd<0||ps_call.fstat_fn(sourcefd,&st)||!S_ISDIR(st.st_mode)||ps_call.fstatfs_fn(sourcefd,&sf)){r.error=errno?errno:EINVAL;goto done;}
 if(sf.f_type!=PSTOREFS_MAGIC||(sf.f_flags&(ST_RDONLY|ST_NOSUID|ST_NODEV|ST_NOEXEC))!=(ST_RDONLY|ST_NOSUID|ST_NODEV|ST_NOEXEC)){r.error=EINVAL;goto done;}
 dev_t source_dev=st.st_dev;
 directory=fdopendir(sourcefd);
 if(!directory){r.error=errno;goto done;}
 sourcefd=-1; /* fdopendir owns it now. */
 r.status="complete";
 for(;;){
  errno=0;struct dirent *entry=readdir(directory);
  if(!entry){if(errno)ps_problem(&r,errno);break;}
  if(!strcmp(entry->d_name,".")||!strcmp(entry->d_name,".."))continue;
  if(r.entries==PS_FILES_MAX){ps_problem(&r,E2BIG);break;}
  if(strlen(entry->d_name)>255){ps_problem(&r,ENAMETOOLONG);break;}
  r.entries++;
  ps_file(dirfd(directory),outdir,source_dev,entry->d_name,&r);
 }
done:
 if(directory&&closedir(directory)){ps_problem(&r,errno);}
 if(sourcefd>=0&&ps_call.close_fn(sourcefd)){ps_problem(&r,errno);}
 /* Close every pstore descriptor before attempting either unmount method. */
 if(mounted){
  if(!call.umount_fn(mountpath,0))unmount_status="clean";
  else {
   int regular_error=errno?errno:EIO;
   if(!call.umount_fn(mountpath,MNT_DETACH)){unmount_status="detached";ps_problem(&r,regular_error);}
   else {unmount_status="residual";ps_problem(&r,errno?errno:EIO);}
  }
 }
 /* No unlink/rmdir of source entries, including on failed or partial copies. */
 if(!strcmp(r.status,"unavailable")&&!r.error)r.error=EIO;
 (void)ps_line(&r,"#summary\tstatus=%s\tfiles=%u\tbytes=%llu\terrno=%d\tunmount=%s\n",r.status,r.files,(unsigned long long)r.bytes,r.error,unmount_status);
 if(manifestfd>=0){
  if(ps_write(manifestfd,r.manifest,r.used))ps_problem(&r,errno);
  if(ps_call.close_fn(manifestfd))ps_problem(&r,errno);
 }
 if(outdir>=0&&ps_call.close_fn(outdir))ps_problem(&r,errno);
 if(rootfd>=0&&ps_call.close_fn(rootfd))ps_problem(&r,errno);
 event(!strcmp(r.status,"complete")?"prior_pstore_snapshot_complete":!strcmp(r.status,"unavailable")?"prior_pstore_snapshot_unavailable":"prior_pstore_snapshot_partial",r.error,"scope=prior-pstore origin_boot_id=unknown status=%s files=%u entries=%u read_bytes=%llu bytes=%llu unmount=%s manifest_path=/r36-report/prior-pstore/manifest.tsv",r.status,r.files,r.entries,(unsigned long long)r.read_bytes,(unsigned long long)r.bytes,unmount_status);
 report_error=old_report_error;stage=old_stage;errno=old_errno;
}
static void prior_pstore_snapshot(void){prior_pstore_snapshot_at(REPORT_ROOT);}
