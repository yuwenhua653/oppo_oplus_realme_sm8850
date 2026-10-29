#define _GNU_SOURCE
/* R36 normal PID1 held-mount handoff. Derived from the R35-proven R33 core. No partition writer, module loader or shell. */
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <sys/statvfs.h>
#include <sys/mount.h>
#include <sys/ioctl.h>
#include <sys/sysmacros.h>
#include <linux/loop.h>
#include <linux/fs.h>
#include <linux/magic.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dirent.h>
#include <signal.h>
#include <stdarg.h>
#include "r36_contract.h"

extern char **environ;
#define BASE "/r32-runtime"
#define MAX_IMAGE (512ULL * 1024 * 1024)
#define DLKM_FLAGS (MS_RDONLY|MS_NOSUID|MS_NODEV)
static unsigned long dlkm_flags(int i){return DLKM_FLAGS|(i?0:MS_NOEXEC);}
static const char *targets[2]={"/system_dlkm","/vendor_dlkm"};
static const char *images[2]={"/r32-payload/system_dlkm.img","/r32-payload/vendor_dlkm.img"};
static const char *hashes[2]={R36_SYSTEM_SHA256,R36_VENDOR_SHA256};
static const uint64_t sizes[2]={R36_SYSTEM_BYTES,R36_VENDOR_BYTES};
static const char recovery_hash[]="b0d438147ce216b24fe142c4ca3545481051144e00df00a5b2a1538676d7b472";
static int logfd=-1, reportfd=-1, report_error=0;
static unsigned sequence;
static char boot_id[40]="unavailable";
static struct stat report_identity;
static const char *stage="entry";
static int recovery_mode,recovery_present,parsed_force=-1;
#define REPORT_ROOT "/r36-report"
#define REPORT_HELD "/vendor_dlkm/r36-report"
static dev_t report_dev;

/* Small SHA-256 implementation, with independently checked test vectors. */
struct sha { uint32_t h[8]; uint64_t len; unsigned used; unsigned char b[64]; };
static const uint32_t K[64]={
0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};
static uint32_t rr(uint32_t x,unsigned n){return (x>>n)|(x<<(32-n));}
static void transform(struct sha *s){
 uint32_t w[64],a,b,c,d,e,f,g,h;
 for(unsigned i=0;i<16;i++)w[i]=((uint32_t)s->b[i*4]<<24)|((uint32_t)s->b[i*4+1]<<16)|((uint32_t)s->b[i*4+2]<<8)|s->b[i*4+3];
 for(unsigned i=16;i<64;i++)w[i]=w[i-16]+(rr(w[i-15],7)^rr(w[i-15],18)^(w[i-15]>>3))+w[i-7]+(rr(w[i-2],17)^rr(w[i-2],19)^(w[i-2]>>10));
 a=s->h[0];b=s->h[1];c=s->h[2];d=s->h[3];e=s->h[4];f=s->h[5];g=s->h[6];h=s->h[7];
 for(unsigned i=0;i<64;i++){uint32_t x=h+(rr(e,6)^rr(e,11)^rr(e,25))+((e&f)^((~e)&g))+K[i]+w[i];uint32_t y=(rr(a,2)^rr(a,13)^rr(a,22))+((a&b)^(a&c)^(b&c));h=g;g=f;f=e;e=d+x;d=c;c=b;b=a;a=x+y;}
 s->h[0]+=a;s->h[1]+=b;s->h[2]+=c;s->h[3]+=d;s->h[4]+=e;s->h[5]+=f;s->h[6]+=g;s->h[7]+=h;
}
static void sha_init(struct sha*s){*s=(struct sha){{0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19},0,0,{0}};}
static void sha_add(struct sha*s,const void*p,size_t n){const unsigned char*q=p;s->len+=n;while(n--){s->b[s->used++]=*q++;if(s->used==64){transform(s);s->used=0;}}}
static void sha_end(struct sha*s,char out[65]){uint64_t bits=s->len*8;s->b[s->used++]=0x80;if(s->used>56){while(s->used<64)s->b[s->used++]=0;transform(s);s->used=0;}while(s->used<56)s->b[s->used++]=0;for(int i=7;i>=0;i--)s->b[s->used++]=(unsigned char)(bits>>(8*i));transform(s);for(unsigned i=0;i<8;i++)snprintf(out+i*8,9,"%08x",s->h[i]);out[64]=0;}
static int bad(void){errno=EINVAL;return -1;}
struct calls {
 int (*ioctl_fn)(int,unsigned long,void*);
 int (*mount_fn)(const char*,const char*,const char*,unsigned long,const void*);
 int (*umount_fn)(const char*,int);
 int (*close_fn)(int);
 int (*open_fn)(const char*,int);
 int (*lstat_fn)(const char*,struct stat*);
 int (*statfs_fn)(const char*,struct statfs*);
 int (*statvfs_fn)(const char*,struct statvfs*);
 int (*exec_fn)(const char*,char*const[],char*const[]);
 ssize_t (*write_fn)(int,const void*,size_t);
};
static int real_ioctl(int fd,unsigned long req,void*p){return ioctl(fd,req,p);}
static int real_open(const char*p,int f){return open(p,f);}
static struct calls call={real_ioctl,mount,umount2,close,real_open,lstat,statfs,statvfs,execve,write};
static void pmsg_event(const char*,size_t);
static void event(const char*name,int err,const char*fmt,...){
 int saved=errno; char detail[2048],line[2560];va_list ap;va_start(ap,fmt);
 int d=vsnprintf(detail,sizeof(detail),fmt,ap);va_end(ap);
 if(d<0||(size_t)d>=sizeof(detail)){report_error=EOVERFLOW;errno=saved;return;}
 int n=snprintf(line,sizeof(line),"R36_PROBE build_id=%s seq=%u event=%s stage=%s errno=%d boot_id=%s%s%s\n",R36_BUILD_ID,++sequence,name,stage,err,boot_id,d?" ":"",detail);
 if(n<0||(size_t)n>=sizeof(line)){report_error=EOVERFLOW;errno=saved;return;}
 if(reportfd>=0){size_t off=0;while(off<(size_t)n){ssize_t w=call.write_fn(reportfd,line+off,(size_t)n-off);if(w<0&&errno==EINTR)continue;if(w<=0){report_error=errno?errno:EIO;break;}off+=(size_t)w;}}
 else report_error=EBADF;
 if(logfd>=0)(void)!write(logfd,line,(size_t)n);
 pmsg_event(line,(size_t)n);
 errno=saved;
}
static void phase(const char*p){stage=p;event("step",0,"");}
static int mismatch(const char*what){event("mismatch",EINVAL,"check=%s",what);return bad();}
static void input_text(const char*source,const char*text){
 unsigned part=0;const unsigned char*p=(const unsigned char*)text;
 do{char out[1400];size_t used=0;while(*p&&used+5<sizeof(out)){unsigned c=*p++;if(c>32&&c<127&&c!='\\')out[used++]=(char)c;else{snprintf(out+used,5,"\\x%02x",c);used+=4;}}out[used]=0;event("observe",0,"source=%s part=%u text=%s",source,part++,used?out:"<empty>");}while(*p);
}
#include "pstore_snapshot.h"
static int hash_fd(int fd,uint64_t expected,const char*expected_hash,int elf){
 struct stat st;unsigned char b[65536];uint64_t count=0;struct sha s;char hex[65];
 if(fstat(fd,&st))return -1;
 event("observe",0,"object=file fd=%d mode=%o uid=%u gid=%u size=%lld dev=%u:%u inode=%llu",fd,st.st_mode,st.st_uid,st.st_gid,(long long)st.st_size,major(st.st_dev),minor(st.st_dev),(unsigned long long)st.st_ino);
 if(!S_ISREG(st.st_mode)||st.st_uid||st.st_gid||(st.st_mode&022)||st.st_size<0||(uint64_t)st.st_size!=expected||expected>MAX_IMAGE||strlen(expected_hash)!=64)return mismatch("file-metadata");
 sha_init(&s);for(;;){ssize_t n=read(fd,b,sizeof(b));if(n<0)return -1;if(!n)break;if(!count&&elf&&(n<4||memcmp(b,"\177ELF",4)))return mismatch("elf-magic");count+=(uint64_t)n;if(count>expected)return mismatch("file-overlong");sha_add(&s,b,(size_t)n);}sha_end(&s,hex);
 event("observe",0,"object=sha256 value=%s bytes=%llu",hex,(unsigned long long)count);
 if(count!=expected||strcmp(hex,expected_hash))return mismatch("file-sha256");
 return lseek(fd,0,SEEK_SET)==0?0:-1;
}
static int open_verified(const char*p,uint64_t size,const char*hash,int elf){int fd=open(p,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);if(fd<0)return -1;if(hash_fd(fd,size,hash,elf)){int e=errno;close(fd);errno=e;return -1;}return fd;}
static int secure_dir(const char*p,dev_t expected){struct stat st;if(call.lstat_fn(p,&st))return -1;event("observe",0,"object=directory path=%s mode=%o uid=%u gid=%u dev=%u:%u expected_dev=%u:%u",p,st.st_mode,st.st_uid,st.st_gid,major(st.st_dev),minor(st.st_dev),major(expected),minor(expected));if(!S_ISDIR(st.st_mode)||st.st_uid||st.st_gid||(st.st_mode&022)||st.st_dev!=expected)return mismatch("directory-metadata");return 0;}
static int empty_dir(const char*p,dev_t expected){if(secure_dir(p,expected))return -1;DIR*d=opendir(p);if(!d)return -1;struct dirent*x;int r=0;errno=0;while((x=readdir(d))){if(strcmp(x->d_name,".")&&strcmp(x->d_name,"..")){r=mismatch("directory-not-empty");break;}}if(!r&&errno)r=-1;int e=errno;closedir(d);errno=e;return r;}
static int read_small(const char*p,char*b,size_t cap){int fd=open(p,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);if(fd<0)return -1;size_t used=0;int r=0;while(used<cap){ssize_t n=read(fd,b+used,cap-used);if(n<0){r=-1;break;}if(!n)break;used+=(size_t)n;}int e=errno;if(close(fd)&&!r){r=-1;e=errno;}errno=e;if(r)return -1;if(used>=cap)return mismatch("input-truncated");b[used]=0;return 0;}
#include "pmsg_stages.h"
static int parse_dev(const char*s,dev_t*out){unsigned a,b;char extra;if(sscanf(s,"%u:%u %c",&a,&b,&extra)!=2||a>0xfff||b>0xfffff)return mismatch("device-number");*out=makedev(a,b);return 0;}
static int node(const char*p,mode_t type,dev_t device){struct stat st;if(mknod(p,type|0600,device))return -1;if(lstat(p,&st))return -1;if((st.st_mode&S_IFMT)!=type||st.st_uid||st.st_gid||st.st_rdev!=device||(st.st_mode&0777)!=0600)return mismatch("private-node");return 0;}
struct mode_counts{unsigned rd,rc,mode,bootmode,force;int force_value,mode_value,bootmode_value;};
static int mode_value(struct mode_counts*c,const char*k,const char*v){
 if(!strcmp(k,"rdinit"))return (!strcmp(v,"/r36-init")&&++c->rd==1)?0:mismatch("rdinit");
 if(!strcmp(k,"androidboot.init_rc"))return (!strcmp(v,"/vendor_dlkm/r32/init.rc")&&++c->rc==1)?0:mismatch("init-rc");
 if(!strcmp(k,"androidboot.mode")){if(++c->mode!=1)return mismatch("duplicate-mode");c->mode_value=!strcmp(v,"normal")?1:!strcmp(v,"recovery")?2:0;return c->mode_value?0:mismatch("mode-value");}
 if(!strcmp(k,"androidboot.bootmode")){if(++c->bootmode!=1)return mismatch("duplicate-bootmode");c->bootmode_value=!strcmp(v,"normal")?1:!strcmp(v,"recovery")?2:0;return c->bootmode_value?0:mismatch("bootmode-value");}
 if(!strcmp(k,"androidboot.force_normal_boot")){if(++c->force!=1||strlen(v)!=1||(v[0]!='0'&&v[0]!='1'))return mismatch("force-normal-boot");c->force_value=v[0]-'0';return 0;}
 return 0;
}
static int sensitive_key(const char*t){return strstr(t,"rdinit")||strstr(t,"androidboot.init_rc")||strstr(t,"androidboot.mode")||strstr(t,"androidboot.bootmode")||strstr(t,"androidboot.force_normal_boot");}
static int check_mode(char*cmd,char*boot){
 struct mode_counts c={.force_value=-1};char*save=NULL;
 for(char*t=strtok_r(cmd," \t\r\n",&save);t;t=strtok_r(NULL," \t\r\n",&save)){char*eq=strchr(t,'=');if(!eq){if(sensitive_key(t))return mismatch("malformed-cmdline-key");continue;}*eq++=0;if(mode_value(&c,t,eq))return -1;}
 /* Kernel rdinit must come from the actual kernel cmdline, not bootconfig. */
 if(c.rd!=1)return mismatch("missing-cmdline-rdinit");
 save=NULL;for(char*t=strtok_r(boot,"\n",&save);t;t=strtok_r(NULL,"\n",&save)){char k[128],v[256];int used=-1;int n=sscanf(t," %127[^= \t] = \"%255[^\"]\" %n",k,v,&used);if(n==2&&used>=0&&!t[used]){if(mode_value(&c,k,v))return -1;}else if(sensitive_key(t))return mismatch("malformed-bootconfig-key");}
 if(c.rc!=1)return mismatch("missing-init-rc");
 recovery_mode=recovery_present&&c.force_value!=1;parsed_force=c.force_value;
 int selected=recovery_mode?2:1;
 if((c.mode&&c.mode_value!=selected)||(c.bootmode&&c.bootmode_value!=selected))return mismatch("mode-branch-conflict");
 return 0;
}
struct state{int img[2],loop[2],owned[2],mounted[2],touched[2],sys,proc,sys_touched,proc_touched,ctl,report_mounted,report_moved,report_original,report_order_verified;dev_t dev[2],rootdev;long rootfs;struct stat backing[2];char node[2][80];};
static struct state state_init(void){struct state s={.img={-1,-1},.loop={-1,-1},.ctl=-1};return s;}
static int normal_pmsg_setup(struct state*s,int mode_checked){
 /* Before mode parsing, only an authenticated ramdisk without Recovery is a
  * candidate. A Recovery-containing ramdisk must first pass the normal gate. */
 if(recovery_mode||(!mode_checked&&recovery_present))return 0;
 if(!s->sys){phase("private-sysfs");if(call.mount_fn("sysfs",BASE"/sys","sysfs",MS_RDONLY|MS_NOSUID|MS_NODEV|MS_NOEXEC,NULL))return -1;s->sys=s->sys_touched=1;}
 pmsg_start(1,s->rootdev);return 0;
}
static int configure_loop(struct state*s,int i){struct loop_config c;memset(&c,0,sizeof(c));c.fd=(uint32_t)s->img[i];c.info.lo_flags=LO_FLAGS_READ_ONLY|LO_FLAGS_AUTOCLEAR;event("observe",0,"loop=%d request_flags=%u backing_fd=%u",i,c.info.lo_flags,c.fd);if(call.ioctl_fn(s->loop[i],LOOP_CONFIGURE,&c))return -1;s->owned[i]=1;return 0;}
static int verify_loop(struct state*s,int i){
 struct loop_info64 li;int ro=0;uint64_t size=0;unsigned required=LO_FLAGS_READ_ONLY|LO_FLAGS_AUTOCLEAR;if(!s->owned[i])return mismatch("unowned-loop");memset(&li,0,sizeof(li));
 phase(i?"vendor-loop-status":"system-loop-status");if(call.ioctl_fn(s->loop[i],LOOP_GET_STATUS64,&li))return -1;
 event("observe",0,"loop=%d flags=%u inode=%llu backing_dev=%llu offset=%llu sizelimit=%llu encrypt=%u",i,li.lo_flags,(unsigned long long)li.lo_inode,(unsigned long long)li.lo_device,(unsigned long long)li.lo_offset,(unsigned long long)li.lo_sizelimit,li.lo_encrypt_type);
 if((li.lo_flags&required)!=required||(li.lo_flags&~(required|LO_FLAGS_PARTSCAN))||li.lo_inode!=s->backing[i].st_ino||li.lo_device!=(uint64_t)s->backing[i].st_dev||li.lo_offset||li.lo_sizelimit||li.lo_encrypt_type)return mismatch("loop-status");
 phase(i?"vendor-loop-readonly":"system-loop-readonly");if(call.ioctl_fn(s->loop[i],BLKROGET,&ro))return -1;event("observe",0,"loop=%d readonly=%d",i,ro);if(ro!=1)return mismatch("loop-readonly");
 phase(i?"vendor-loop-size":"system-loop-size");if(call.ioctl_fn(s->loop[i],BLKGETSIZE64,&size))return -1;event("observe",0,"loop=%d bytes=%llu",i,(unsigned long long)size);return size==sizes[i]?0:mismatch("loop-size");
}
static int mount_dlkm(struct state*s,int i){if(!s->owned[i])return mismatch("mount-unowned-loop");if(call.mount_fn(s->node[i],targets[i],"ext4",dlkm_flags(i),"noload"))return -1;s->mounted[i]=1;s->touched[i]=1;return 0;}
static int verify_mount(struct state*s,int i){
 struct stat st;struct statfs sf;struct statvfs sv;char p[80];unsigned long expected=ST_RDONLY|ST_NOSUID|ST_NODEV|(i?0:ST_NOEXEC);
 phase(i?"vendor-mount-stat":"system-mount-stat");if(call.lstat_fn(targets[i],&st))return -1;event("observe",0,"mount=%s dev=%u:%u expected_dev=%u:%u",targets[i],major(st.st_dev),minor(st.st_dev),major(s->dev[i]),minor(s->dev[i]));if(st.st_dev!=s->dev[i])return mismatch("mounted-device");
 phase(i?"vendor-mount-statfs":"system-mount-statfs");if(call.statfs_fn(targets[i],&sf))return -1;event("observe",0,"mount=%s fs_type=%lx",targets[i],(unsigned long)sf.f_type);if(sf.f_type!=EXT4_SUPER_MAGIC)return mismatch("mounted-filesystem");
 phase(i?"vendor-mount-statvfs":"system-mount-statvfs");if(call.statvfs_fn(targets[i],&sv))return -1;event("observe",0,"mount=%s flags=%lu expected_masked_flags=%lu",targets[i],sv.f_flag,expected);if((sv.f_flag&(ST_RDONLY|ST_NOSUID|ST_NODEV|ST_NOEXEC))!=expected)return mismatch("mounted-flags");
 phase(i?"vendor-modules-directory":"system-modules-directory");snprintf(p,sizeof(p),"%s/lib/modules",targets[i]);if(secure_dir(p,s->dev[i]))return -1;return verify_loop(s,i);
}
static int close_tracked(int*fd,const char*label){if(*fd<0)return 0;int f=*fd;*fd=-1;if(call.close_fn(f)){event("cleanup_error",errno,"operation=close object=%s fd=%d",label,f);return -1;}return 0;}
static int root_restored(struct state*s,const char*p){struct stat st;struct statfs sf;if(call.lstat_fn(p,&st)){event("cleanup_error",errno,"operation=lstat path=%s",p);return -1;}if(call.statfs_fn(p,&sf)){event("cleanup_error",errno,"operation=statfs path=%s",p);return -1;}event("observe",0,"cleanup_path=%s dev=%u:%u fs_type=%lx",p,major(st.st_dev),minor(st.st_dev),(unsigned long)sf.f_type);if(!S_ISDIR(st.st_mode)||st.st_dev!=s->rootdev||sf.f_type!=s->rootfs)return mismatch("cleanup-root-not-restored");return 0;}
static int cleanup(struct state*s){
 int failed=0;
 /* A held child may carry the only readable log. Never unmount its parent. */
 if(s->report_moved){event("cleanup_error",EBUSY,"operation=guard reason=held-report-child");errno=EBUSY;return -1;}
 for(int i=1;i>=0;i--){phase(i?"cleanup-vendor-unmount":"cleanup-system-unmount");if(s->mounted[i]){if(call.umount_fn(targets[i],0)){event("cleanup_error",errno,"operation=umount path=%s",targets[i]);failed=1;}else s->mounted[i]=0;}}
 for(int i=1;i>=0;i--){
  phase(i?"cleanup-vendor-loop-close":"cleanup-system-loop-close");if(close_tracked(&s->loop[i],"loop"))failed=1;
  if(s->owned[i]){phase(i?"cleanup-vendor-loop-unbound":"cleanup-system-loop-unbound");int fd=call.open_fn(s->node[i],O_RDONLY|O_CLOEXEC|O_NOFOLLOW);if(fd<0){event("cleanup_error",errno,"operation=reopen-loop loop=%d",i);failed=1;}
   else{struct loop_info64 li;memset(&li,0,sizeof(li));errno=0;int rc=call.ioctl_fn(fd,LOOP_GET_STATUS64,&li),e=errno;event("observe",e,"cleanup_loop=%d status_rc=%d",i,rc);if(rc!=-1||e!=ENXIO){failed=1;event("cleanup_error",rc<0?e:EBUSY,"operation=verify-loop-unbound loop=%d",i);}else s->owned[i]=0;if(close_tracked(&fd,"loop-verification"))failed=1;}}
  if(close_tracked(&s->img[i],"payload"))failed=1;
 }
 if(close_tracked(&s->ctl,"loop-control"))failed=1;
 phase("cleanup-sysfs-unmount");if(s->sys){if(call.umount_fn(BASE"/sys",0)){event("cleanup_error",errno,"operation=umount path="BASE"/sys");failed=1;}else s->sys=0;}
 phase("cleanup-proc-unmount");if(s->proc){if(call.umount_fn(BASE"/proc",0)){event("cleanup_error",errno,"operation=umount path="BASE"/proc");failed=1;}else s->proc=0;}
 phase("cleanup-root-verification");for(int i=0;i<2;i++)if(s->touched[i]&&root_restored(s,targets[i]))failed=1;
 if(s->sys_touched&&root_restored(s,BASE"/sys"))failed=1;
 if(s->proc_touched&&root_restored(s,BASE"/proc"))failed=1;
 return failed?-1:0;
}
static int pin_file(const char*p,uint64_t size,const char*hash,int elf){int fd=open_verified(p,size,hash,elf);if(fd<0)return -1;return close(fd);}
static int validate_boot_id(char*b){size_t n=strlen(b);if(n&&b[n-1]=='\n')b[--n]=0;if(n!=36)return bad();for(size_t i=0;i<36;i++){if(i==8||i==13||i==18||i==23){if(b[i]!='-')return bad();}else if(!((b[i]>='0'&&b[i]<='9')||(b[i]>='a'&&b[i]<='f')))return bad();}return 0;}
static int (*pin_path)(const char*,uint64_t,const char*,int)=pin_file;
static int (*empty_path)(const char*,dev_t)=empty_dir;
static int verify_report(const char *path){
 struct stat st;struct statfs sf;struct statvfs sv;char file[160];
 if(call.lstat_fn(path,&st)||call.statfs_fn(path,&sf)||call.statvfs_fn(path,&sv))return -1;
 if(!S_ISDIR(st.st_mode)||st.st_uid||st.st_gid||(st.st_mode&0777)!=0755||st.st_dev!=report_dev||sf.f_type!=TMPFS_MAGIC||(sv.f_flag&(ST_RDONLY|ST_NOSUID|ST_NODEV|ST_NOEXEC))!=(ST_NOSUID|ST_NODEV|ST_NOEXEC))return mismatch("report-mount");
 snprintf(file,sizeof(file),"%s/probe.log",path);if(call.lstat_fn(file,&st))return -1;
 if(!S_ISREG(st.st_mode)||st.st_uid||st.st_gid||(st.st_mode&0777)!=0644||st.st_dev!=report_identity.st_dev||st.st_ino!=report_identity.st_ino)return mismatch("report-log-identity");
 event("observe",0,"report_path=%s report_dev=%u:%u report_inode=%llu",path,major(report_dev),minor(report_dev),(unsigned long long)st.st_ino);return 0;
}
#include "report_reanchor.h"
static int private_cleanup(struct state*s){
 int failed=0;
 phase("private-sysfs-unmount");if(s->sys){if(call.umount_fn(BASE"/sys",0)){event("cleanup_error",errno,"operation=umount path="BASE"/sys");failed=1;}else s->sys=0;}
 phase("private-proc-unmount");if(s->proc){if(call.umount_fn(BASE"/proc",0)){event("cleanup_error",errno,"operation=umount path="BASE"/proc");failed=1;}else s->proc=0;}
 if(s->sys_touched&&root_restored(s,BASE"/sys"))failed=1;
 if(s->proc_touched&&root_restored(s,BASE"/proc"))failed=1;
 if(!failed)event("private_cleanup_verified",0,"dlkm_mounts_retained=%d",!recovery_mode);
 return failed?-1:0;
}
static int retained_mounts(struct state*s){
 int failed=0;
 phase("helper-fds-close");
 for(int i=1;i>=0;i--){if(close_tracked(&s->loop[i],"loop"))failed=1;if(close_tracked(&s->img[i],"payload"))failed=1;}
 if(close_tracked(&s->ctl,"loop-control"))failed=1;
 if(failed)return -1;
 event("helper_fds_closed",0,"loop_fds=0 payload_fds=0 control_fds=0");
 for(int i=0;i<2;i++){
  phase(i?"vendor-retained-reopen":"system-retained-reopen");
  s->loop[i]=call.open_fn(s->node[i],O_RDONLY|O_CLOEXEC|O_NOFOLLOW);if(s->loop[i]<0)return -1;
  if(verify_mount(s,i))return -1;
  if(pin_path(i?R36_MARKER_PATH:R36_SYSTEM_MARKER_PATH,R36_MARKER_BYTES,R36_MARKER_SHA256,0))return -1;
  if(i&&pin_path("/vendor_dlkm/r32/init.rc",R36_RC_BYTES,R36_RC_SHA256,0))return -1;
  if(close_tracked(&s->loop[i],"retained-verification"))return -1;
  event("mounts_retained_verified",0,"target=%s dev=%u:%u expected_bytes=%llu marker_verified=%d helper_loop_fds=0",targets[i],major(s->dev[i]),minor(s->dev[i]),(unsigned long long)sizes[i],1);
 }
 return verify_report(REPORT_HELD);
}
static int helper_mount_snapshot(void){
 char text[65536];phase("helper-mount-snapshot");
 if(read_small(BASE"/proc/self/mountinfo",text,sizeof(text)))return -1;
 input_text("helper-mountinfo",text);
 if(read_small(BASE"/proc/self/mounts",text,sizeof(text)))return -1;
 input_text("helper-mounts",text);
 if(report_error){errno=report_error;return -1;}
 return 0;
}
static void reopen_report(struct state*s){
 int fd=open_report_log(s->report_moved?REPORT_HELD:REPORT_ROOT);if(fd>=0)reportfd=fd;
}
static int native_failure(struct state*s,int e){
 event("native_fail",e,"mode=%s normal_android_boot_verified=0",recovery_mode?"recovery":"normal");
 /* Never unmount vendor while the report is its child; preserve the evidence. */
 if(s->report_moved&&return_report(s)){int move_errno=errno;event("cleanup_failed",move_errno,"reason=report-return-failed dlkm_cleanup_attempted=0");event("halt",move_errno,"reason=cleanup-incomplete");return -1;}
 int cleaned=cleanup(s)==0;
 event(cleaned?"cleanup_verified":"cleanup_failed",cleaned?0:EIO,"dlkm_unmounted=%d normal_handoff_permitted=0",cleaned);
 event("halt",e,"reason=native-failure normal_handoff_permitted=0 report_error=%d",report_error);
 errno=e;return -1;
}
static int handoff(struct state*s,int recovery){
 if(!recovery&&(!s->report_order_verified||!s->report_moved||s->report_original))return native_failure(s,EINVAL);
 phase(recovery?"recovery-handoff":"normal-handoff");
 event(recovery?"recovery_passthrough":"handoff_mounted",0,"target=original-init init_sha256=%s dlkm_mounts_retained=%d mode=%s normal_android_mode_tested=%d normal_android_boot_verified=0",R36_INIT_SHA256,!recovery,recovery?"recovery":"normal",!recovery);
 if(report_error)return native_failure(s,report_error);
 if(close_tracked(&reportfd,"report")){int e=errno?errno:EIO;report_error=e;reopen_report(s);return native_failure(s,e);}
 if(!recovery)pmsg_pre_exec();
 char*av[]={"/init",NULL};int r=call.exec_fn(av[0],av,environ);int e=errno;
 reopen_report(s);event("handoff_failed",e,"exec_rc=%d",r);return native_failure(s,e);
}
/* Accept only the byte-pinned legacy diagnostic RC or restored R95 GUI RC.
 * The normal Android payload/mount/loader path is unchanged. */
static uint64_t recovery_rc_bytes=5341;
static const char *recovery_rc_hash="6631789e0a11de418bb33d0b82dc61638d5269ecb513b4090fd99cd3ed875112";
static int select_recovery_rc_size(uint64_t bytes){
 if(bytes==5341){recovery_rc_bytes=5341;recovery_rc_hash="6631789e0a11de418bb33d0b82dc61638d5269ecb513b4090fd99cd3ed875112";return 0;}
 if(bytes==10292){recovery_rc_bytes=10292;recovery_rc_hash="e04e4323eb7b18e000f4bc227510b18ac86fa5e931502aed77f34150f15a5424";return 0;}
 errno=EINVAL;return -1;
}
static int select_recovery_rc(void){
 struct stat st;
 if(lstat("/system/etc/init/hw/init.rc",&st)||!S_ISREG(st.st_mode)||st.st_size<0)return -1;
 return select_recovery_rc_size((uint64_t)st.st_size);
}
static int recovery_rc_copy(struct state*s){
 int fd=-1,out=-1,r=-1;unsigned char b[8192];struct stat st;
 if(empty_dir("/vendor_dlkm",s->rootdev))return -1;
 fd=open_verified("/system/etc/init/hw/init.rc",recovery_rc_bytes,recovery_rc_hash,0);if(fd<0)return -1;
 if(mkdir("/vendor_dlkm/r32",0755)||secure_dir("/vendor_dlkm/r32",s->rootdev))goto done;
 out=open("/vendor_dlkm/r32/init.rc",O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0644);if(out<0)goto done;
 for(;;){ssize_t n=read(fd,b,sizeof(b));if(n<0){if(errno==EINTR)continue;goto done;}if(!n)break;ssize_t off=0;while(off<n){ssize_t w=write(out,b+off,(size_t)(n-off));if(w<0&&errno==EINTR)continue;if(w<=0)goto done;off+=w;}}
 if(fchmod(out,0644)||fstat(out,&st)||!S_ISREG(st.st_mode)||st.st_uid||st.st_gid||(st.st_mode&0777)!=0644||st.st_dev!=s->rootdev)goto done;
 r=0;
 done:{int e=errno;if(out>=0&&close(out)&&!r){r=-1;e=errno;}if(close(fd)&&!r){r=-1;e=errno;}errno=e;}
 if(!r)r=pin_path("/vendor_dlkm/r32/init.rc",recovery_rc_bytes,recovery_rc_hash,0);
 return r;
}
static int run_boot(void){
 struct state s=state_init();struct stat root,rs,recovery;struct statfs rf;char b[256],cmd[16384],boot[65536];
 if(getpid()!=1||getuid()!=0||getgid()!=0)return bad();
 if(lstat("/",&root)||statfs("/",&rf)||(rf.f_type!=RAMFS_MAGIC&&rf.f_type!=TMPFS_MAGIC))return bad();
 s.rootdev=root.st_dev;s.rootfs=rf.f_type;
 if(lstat(REPORT_ROOT,&rs)||!S_ISDIR(rs.st_mode)||rs.st_uid||rs.st_gid||(rs.st_mode&0777)!=0755||rs.st_dev!=root.st_dev)return bad();
 /* Verify emptiness without logging before a writable report exists. */
 DIR*d=opendir(REPORT_ROOT);if(!d)return -1;struct dirent*x;int nonempty=0;errno=0;while((x=readdir(d)))if(strcmp(x->d_name,".")&&strcmp(x->d_name,".."))nonempty=1;int readdir_errno=errno;if(closedir(d)||nonempty||readdir_errno)return bad();
 if(call.mount_fn("tmpfs",REPORT_ROOT,"tmpfs",MS_NOSUID|MS_NODEV|MS_NOEXEC,"size=8m,mode=0755"))return -1;
 s.report_mounted=s.report_original=1;
 if(lstat(REPORT_ROOT,&rs))return -1;
 report_dev=rs.st_dev;
 reportfd=open(REPORT_ROOT"/probe.log",O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0644);if(reportfd<0)return -1;
 if(fstat(reportfd,&report_identity))return -1;
 event("start",0,"root_dev=%u:%u rootfs_type=%lx normal_android_boot_verified=0",major(root.st_dev),minor(root.st_dev),(unsigned long)rf.f_type);
 if(verify_report(REPORT_ROOT)||report_dev==s.rootdev)goto failed;
 phase("generic-init-hash");if(pin_path("/init",R36_INIT_BYTES,R36_INIT_SHA256,1))goto failed;
 phase("recovery-detection");if(lstat("/system/bin/recovery",&recovery)==0){recovery_present=1;if(pin_path("/system/bin/recovery",4063256,recovery_hash,1))goto failed;if(select_recovery_rc())goto failed;}else if(errno!=ENOENT&&errno!=ENOTDIR)goto failed;
 phase("root-directories");if(secure_dir(BASE,s.rootdev)||empty_dir(BASE"/sys",s.rootdev)||empty_dir(BASE"/proc",s.rootdev)||empty_dir(BASE"/dev",s.rootdev)||empty_dir(targets[0],s.rootdev)||empty_dir(targets[1],s.rootdev)||secure_dir("/r32-payload",s.rootdev))goto failed;
 phase("log-node");if(node(BASE"/dev/kmsg",S_IFCHR,makedev(1,11)))goto failed;logfd=open(BASE"/dev/kmsg",O_WRONLY|O_NONBLOCK|O_CLOEXEC|O_NOFOLLOW);if(logfd<0)goto failed;
 phase("private-proc");if(call.mount_fn("proc",BASE"/proc","proc",MS_RDONLY|MS_NOSUID|MS_NODEV|MS_NOEXEC,NULL))goto failed;s.proc=s.proc_touched=1;
 phase("boot-id");if(read_small(BASE"/proc/sys/kernel/random/boot_id",b,sizeof(b))||validate_boot_id(b))goto failed;strcpy(boot_id,b);event("observe",0,"object=boot-id");
 if(normal_pmsg_setup(&s,0))goto failed;
 phase("boot-mode");if(read_small(BASE"/proc/cmdline",cmd,sizeof(cmd)))goto failed;if(read_small(BASE"/proc/bootconfig",boot,sizeof(boot))){if(errno!=ENOENT)goto failed;boot[0]=0;}input_text("cmdline",cmd);input_text("bootconfig",boot);if(check_mode(cmd,boot))goto failed;
 event("mode_verified",0,"mode=%s selected_mode=%s recovery_present=%d force_present=%d force_value=%s",recovery_mode?"recovery":"normal",recovery_mode?"recovery":"normal",recovery_present,parsed_force>=0,parsed_force<0?"absent":parsed_force?"1":"0");
 if(recovery_present){phase("embedded-recovery-original-rc-hash");if(pin_path("/system/etc/init/hw/init.rc",recovery_rc_bytes,recovery_rc_hash,0))goto failed;
  if(!recovery_mode)event("embedded_recovery_verified",0,"mode=normal recovery_sha256=%s rc_sha256=%s",recovery_hash,recovery_rc_hash);
 }
 if(recovery_mode){
  phase("recovery-original-rc-hash");if(pin_path("/system/etc/init/hw/init.rc",recovery_rc_bytes,recovery_rc_hash,0))goto failed;
  event("recovery_identity_verified",0,"mode=recovery normal_android_mode_tested=0 init_sha256=%s recovery_sha256=%s rc_sha256=%s",R36_INIT_SHA256,recovery_hash,recovery_rc_hash);
  prior_pstore_snapshot();
  phase("recovery-rc-copy");if(recovery_rc_copy(&s)||private_cleanup(&s))goto failed;
  return handoff(&s,1);
 }
 if(normal_pmsg_setup(&s,1))goto failed;
 for(int i=0;i<2;i++){phase(i?"vendor-payload-hash":"system-payload-hash");if(sizes[i]<4096||sizes[i]>MAX_IMAGE||(sizes[i]%4096)){mismatch("payload-size-contract");goto failed;}s.img[i]=open_verified(images[i],sizes[i],hashes[i],0);if(s.img[i]<0||fstat(s.img[i],&s.backing[i]))goto failed;}
 event("identity_verified",0,"mode=normal normal_android_mode_tested=1 init_sha256=%s system_sha256=%s vendor_sha256=%s normal_android_boot_verified=0",R36_INIT_SHA256,hashes[0],hashes[1]);
 phase("loop-control-sysfs");dev_t control;if(read_small(BASE"/sys/class/misc/loop-control/dev",b,sizeof(b)))goto failed;input_text("loop-control-dev",b);if(parse_dev(b,&control)||control!=makedev(10,237)){mismatch("loop-control-device");goto failed;}
 phase("loop-control-node");if(node(BASE"/dev/loop-control",S_IFCHR,control))goto failed;
 phase("loop-control-open");s.ctl=open(BASE"/dev/loop-control",O_RDWR|O_CLOEXEC|O_NOFOLLOW);if(s.ctl<0)goto failed;
 for(int i=0;i<2;i++){
  phase(i?"vendor-loop-get-free":"system-loop-get-free");int index=call.ioctl_fn(s.ctl,LOOP_CTL_GET_FREE,NULL);if(index<0)goto failed;event("observe",0,"loop=%d free_index=%d",i,index);if(index>1048575){mismatch("loop-index-bound");goto failed;}
  phase(i?"vendor-loop-sysfs":"system-loop-sysfs");char p[128];snprintf(p,sizeof(p),BASE"/sys/block/loop%d/dev",index);if(read_small(p,b,sizeof(b)))goto failed;input_text("loop-dev",b);if(parse_dev(b,&s.dev[i])||major(s.dev[i])!=7||(i&&s.dev[i]==s.dev[0])){mismatch("loop-device");goto failed;}
  phase(i?"vendor-loop-node":"system-loop-node");snprintf(s.node[i],sizeof(s.node[i]),BASE"/dev/loop%d",index);if(node(s.node[i],S_IFBLK,s.dev[i]))goto failed;
  phase(i?"vendor-loop-open":"system-loop-open");s.loop[i]=open(s.node[i],O_RDONLY|O_CLOEXEC|O_NOFOLLOW);if(s.loop[i]<0)goto failed;
  phase(i?"vendor-loop-configure":"system-loop-configure");if(configure_loop(&s,i)||verify_loop(&s,i))goto failed;
  phase(i?"vendor-mount":"system-mount");if(mount_dlkm(&s,i)||verify_mount(&s,i))goto failed;event("mounted_verified",0,"target=%s",targets[i]);
 }
 phase("payload-markers");if(pin_path(R36_SYSTEM_MARKER_PATH,R36_MARKER_BYTES,R36_MARKER_SHA256,0)||pin_path(R36_MARKER_PATH,R36_MARKER_BYTES,R36_MARKER_SHA256,0)||pin_path("/vendor_dlkm/r32/init.rc",R36_RC_BYTES,R36_RC_SHA256,0))goto failed;
 if(reanchor_report(&s)||retained_mounts(&s)||helper_mount_snapshot()||private_cleanup(&s))goto failed;
 return handoff(&s,0);
 failed:{int e=errno?errno:EIO;return native_failure(&s,e);}
}
#ifndef R36_UNIT_TEST
int main(int argc,char**argv){if(argc>1&&!strcmp(argv[1],"--help")){puts("R36 normal PID1 held-mount handoff; rdinit=/r36-init; no partition writes");return 0;}if(run_boot()){int e=errno;event("halt",e,"reason=run-boot-returned");pmsg_finish("native_halt");if(getpid()!=1)return 2;for(;;)pause();}return 2;}
#endif
