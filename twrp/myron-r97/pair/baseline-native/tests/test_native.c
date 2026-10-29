#define R36_UNIT_TEST
#include "../r36_init.c"
#include <assert.h>
#include <setjmp.h>

static char output[524288];static size_t used;
static int bad_fstat,bad_held_fs,bad_held_flags,moved,original,fd_place[1000],fail_bind,fail_report_open,fail_fstat,fail_order,bad_order,bad_parent,report_opens,root_unmounts,held_unmounts,mounted[2],fail_move,fail_close,fail_pin,fail_write,fail_reopen,bad_loop,bad_report,fail_umount_at,execs,moves,unmounts,pins,opens,close_log[64],closes;
static jmp_buf executed;
static struct state *active;
static ssize_t mw(int fd,const void*b,size_t n){assert(fd>=900&&fd<1000);if(fail_write){errno=ENOSPC;return -1;}assert(used+n<sizeof(output));memcpy(output+used,b,n);used+=n;output[used]=0;return (ssize_t)n;}
static int mc(int fd){assert(closes<64);close_log[closes++]=fd;if(fd>=900)fd_place[fd]=0;if(fd==fail_close){errno=EIO;return -1;}return 0;}
static int mo(const char*p,int flags){
 if(strstr(p,"/probe.log")){assert(flags==(O_WRONLY|O_APPEND|O_CLOEXEC|O_NOFOLLOW));report_opens++;if(fail_report_open==report_opens){errno=EIO;return -1;}int fd=900+report_opens;fd_place[fd]=strstr(p,REPORT_HELD)?2:1;return fd;}
 assert(flags==(O_RDONLY|O_CLOEXEC|O_NOFOLLOW));opens++;if(fail_reopen){errno=ENOENT;return -1;}if(!strcmp(p,BASE"/dev/loop0"))return 200;if(!strcmp(p,BASE"/dev/loop1"))return 201;assert(0);return -1;
}
static int mfs(int fd,struct stat *st){assert(fd>=900&&fd_place[fd]);if(fail_fstat==report_opens){errno=EIO;return -1;}memset(st,0,sizeof(*st));st->st_mode=S_IFREG|0644;st->st_dev=report_dev;st->st_ino=800;if(bad_fstat&&report_opens==1){if(bad_fstat==1)st->st_ino++;if(bad_fstat==2)st->st_dev++;if(bad_fstat==3)st->st_uid=1;if(bad_fstat==4)st->st_mode=S_IFREG|0600;}return 0;}
static int ml(const char*p,struct stat*st){memset(st,0,sizeof(*st));st->st_mode=S_IFDIR|0755;st->st_dev=makedev(0,2);
 if(strstr(p,"/probe.log")){st->st_mode=S_IFREG|(bad_report?0600:0644);st->st_dev=report_dev;st->st_ino=800;return 0;}
 if((!strcmp(p,REPORT_ROOT)&&original)||(!strcmp(p,REPORT_HELD)&&moved)){st->st_dev=report_dev;return 0;}
 for(int i=0;i<2;i++)if(strncmp(p,targets[i],strlen(targets[i]))==0){if(mounted[i])st->st_dev=active->dev[i];return 0;}
 return 0;}
static int mf(const char*p,struct statfs*sf){memset(sf,0,sizeof(*sf));sf->f_type=TMPFS_MAGIC;
 if(!strcmp(p,REPORT_HELD)&&moved){if(bad_held_fs)sf->f_type=EXT4_SUPER_MAGIC;return 0;}
 for(int i=0;i<2;i++)if(!strcmp(p,targets[i])&&mounted[i])sf->f_type=EXT4_SUPER_MAGIC;
 return 0;}
static int mv(const char*p,struct statvfs*sv){memset(sv,0,sizeof(*sv));sv->f_flag=ST_NOSUID|ST_NODEV|ST_NOEXEC;if(!strcmp(p,REPORT_HELD)&&moved&&bad_held_flags)sv->f_flag|=ST_RDONLY;if(!strcmp(p,targets[0]))sv->f_flag|=ST_RDONLY;else if(!strcmp(p,targets[1]))sv->f_flag=ST_RDONLY|ST_NOSUID|ST_NODEV;return 0;}
static int mm(const char*from,const char*to,const char*fs,unsigned long flags,const void*data){
 assert(!fs&&!data);
 if(flags==MS_BIND){assert(!strcmp(from,REPORT_ROOT)&&!strcmp(to,REPORT_HELD)&&original&&!moved);if(fail_bind){errno=EBUSY;return -1;}moved=1;return 0;}
 assert(flags==MS_MOVE);moves++;if(fail_move==moves){errno=EBUSY;return -1;}
 assert(moved&&!original&&!strcmp(from,REPORT_HELD)&&!strcmp(to,REPORT_ROOT));moved=0;original=1;for(int fd=900;fd<1000;fd++)if(fd_place[fd]==2)fd_place[fd]=1;return 0;
}
static int mu(const char*p,int flags){assert(!flags);unmounts++;
 if(fail_umount_at==unmounts){errno=EBUSY;return -1;}
 if(!strcmp(p,REPORT_ROOT)){assert(original);for(int fd=900;fd<1000;fd++)assert(fd_place[fd]!=1);original=0;root_unmounts++;return 0;}
 if(!strcmp(p,REPORT_HELD)){assert(original&&moved);for(int fd=900;fd<1000;fd++)assert(fd_place[fd]!=2);moved=0;held_unmounts++;return 0;}
 if(!strcmp(p,targets[1])){assert(!moved);mounted[1]=0;}else if(!strcmp(p,targets[0]))mounted[0]=0;else assert(!strcmp(p,BASE"/sys")||!strcmp(p,BASE"/proc"));return 0;
}
static int mrt(const char *p,char *text,size_t cap){
 if(fail_order){errno=EIO;return -1;}const char *mi="1 99 0:2 / / rw - rootfs rootfs rw\n4 1 7:0 / /system_dlkm ro - ext4 loop0 ro\n5 1 7:8 / /vendor_dlkm ro - ext4 loop1 ro\n6 5 0:50 / /vendor_dlkm/r36-report rw - tmpfs tmpfs rw\n";
 const char *mt="rootfs / rootfs rw 0 0\nloop0 /system_dlkm ext4 ro 0 0\nloop1 /vendor_dlkm ext4 ro 0 0\ntmpfs /vendor_dlkm/r36-report tmpfs rw 0 0\n";
 if(bad_order){mi="1 99 0:2 / / rw - rootfs rootfs rw\n2 5 0:50 / /vendor_dlkm/r36-report rw - tmpfs tmpfs rw\n4 1 7:0 / /system_dlkm ro - ext4 loop0 ro\n5 1 7:8 / /vendor_dlkm ro - ext4 loop1 ro\n";}
 assert(strlen(strstr(p,"mountinfo")?mi:mt)<cap);strcpy(text,strstr(p,"mountinfo")?mi:mt);
 if(bad_parent&&strstr(p,"mountinfo")){char *parent=strstr(text,"6 5 0:50");assert(parent);parent[2]='1';}return 0;
}
static int mi(int fd,unsigned long op,void*p){int i=fd==200?0:fd==201?1:fd==10?0:fd==11?1:-1;assert(i>=0);
 if(op==LOOP_GET_STATUS64){if(!mounted[i]){errno=ENXIO;return -1;}struct loop_info64*li=p;memset(li,0,sizeof(*li));li->lo_flags=LO_FLAGS_READ_ONLY|LO_FLAGS_AUTOCLEAR|LO_FLAGS_PARTSCAN;li->lo_inode=active->backing[i].st_ino;li->lo_device=active->backing[i].st_dev;if(bad_loop)li->lo_inode++;return 0;}
 if(op==BLKROGET){*(int*)p=1;return 0;}if(op==BLKGETSIZE64){*(uint64_t*)p=sizes[i];return 0;}assert(!"unexpected ioctl including LOOP_CLR_FD");return -1;}
static int mp(const char*p,uint64_t bytes,const char*hash,int elf){assert(!elf);pins++;if(fail_pin){errno=EIO;return -1;}if(!strcmp(p,R36_MARKER_PATH)||!strcmp(p,R36_SYSTEM_MARKER_PATH)){assert(bytes==29&&!strcmp(hash,R36_MARKER_SHA256));}else{assert(!strcmp(p,"/vendor_dlkm/r32/init.rc")&&bytes==R36_RC_BYTES&&!strcmp(hash,R36_RC_SHA256));}return 0;}
static int me(const char*p,dev_t dev){if(!strcmp(p,REPORT_HELD)){assert(dev==active->dev[1]&&!moved);}else assert(!strcmp(p,REPORT_ROOT)&&dev==active->rootdev&&!original);return 0;}
static int mx(const char*p,char*const av[],char*const env[]){(void)env;assert(!strcmp(p,"/init")&&!strcmp(av[0],"/init")&&!av[1]);execs++;longjmp(executed,1);}
static void reset(struct state*s){used=0;output[0]=0;moved=fail_move=fail_close=fail_pin=fail_write=fail_reopen=bad_loop=bad_report=fail_umount_at=execs=moves=unmounts=pins=opens=closes=0;original=1;bad_fstat=bad_held_fs=bad_held_flags=0;memset(fd_place,0,sizeof(fd_place));fd_place[900]=1;fail_bind=fail_report_open=fail_fstat=fail_order=bad_order=bad_parent=report_opens=root_unmounts=held_unmounts=0;mounted[0]=mounted[1]=1;recovery_mode=recovery_present=0;parsed_force=-1;reportfd=900;logfd=-1;report_error=0;sequence=0;strcpy(boot_id,"11111111-2222-3333-4444-555555555555");stage="fixture";report_dev=makedev(0,50);memset(&report_identity,0,sizeof(report_identity));report_identity.st_dev=report_dev;report_identity.st_ino=800;*s=state_init();s->rootdev=makedev(0,2);s->rootfs=TMPFS_MAGIC;s->sys=s->proc=s->sys_touched=s->proc_touched=s->report_mounted=s->report_original=1;s->ctl=50;
 for(int i=0;i<2;i++){s->loop[i]=10+i;s->img[i]=20+i;s->owned[i]=s->mounted[i]=s->touched[i]=1;s->dev[i]=makedev(7,(unsigned)i*8);s->backing[i].st_ino=100+i;s->backing[i].st_dev=s->rootdev;snprintf(s->node[i],sizeof(s->node[i]),BASE"/dev/loop%d",i);}
 active=s;call=(struct calls){mi,mm,mu,mc,mo,ml,mf,mv,mx,mw};pin_path=mp;empty_path=me;report_fstat=mfs;read_mount_text=mrt;}
static void save(const char*name){FILE*f=fopen(name,"wb");assert(f);assert(fwrite(output,1,used,f)==used);assert(!fclose(f));}
static void events(void){stage="entry";event("start",0,"normal_android_boot_verified=0");stage="fixture";event("mode_verified",0,"mode=normal selected_mode=normal recovery_present=0 force_present=0 force_value=absent");event("identity_verified",0,"mode=normal normal_android_mode_tested=1 init_sha256=%s system_sha256=%s vendor_sha256=%s normal_android_boot_verified=0",R36_INIT_SHA256,hashes[0],hashes[1]);event("mounted_verified",0,"target=/system_dlkm");event("mounted_verified",0,"target=/vendor_dlkm");}
static int mode(const char*c,const char*b,int recovery){char cmd[2048],boot[4096];strcpy(cmd,c);strcpy(boot,b);recovery_present=recovery;return check_mode(cmd,boot);}
static void test_modes(void){struct state s;reset(&s);const char*rc="androidboot.init_rc = \"/vendor_dlkm/r32/init.rc\"\r\n";
 assert(!mode("rdinit=/r36-init",rc,0));assert(!mode("rdinit=/r36-init androidboot.force_normal_boot=1 androidboot.mode=normal",rc,0));assert(!mode("rdinit=/r36-init androidboot.force_normal_boot=0",rc,0));assert(mode("rdinit=/r36-init androidboot.mode=recovery",rc,0));assert(mode("rdinit=/r36-init androidboot.bootmode=charger",rc,0));assert(mode("rdinit=/r36-init rdinit=/r36-init",rc,0));assert(mode("rdinit=/r36-init androidboot.init_rc=/vendor_dlkm/r32/init.rc",rc,0));assert(mode("rdinit=/r33-init",rc,0));assert(mode("rdinit=/r36-init","androidboot.init_rc = /vendor_dlkm/r32/init.rc\n",0));assert(mode("rdinit=/r36-init","androidboot.init_rc = \"/vendor_dlkm/r32/init.rc\" trailing\n",0));
 assert(!mode("rdinit=/r36-init",rc,1));assert(!mode("rdinit=/r36-init androidboot.force_normal_boot=0 androidboot.mode=recovery",rc,1));assert(!mode("rdinit=/r36-init androidboot.force_normal_boot=1",rc,1)&&!recovery_mode);assert(!mode("rdinit=/r36-init androidboot.force_normal_boot=1 androidboot.mode=normal",rc,1)&&!recovery_mode);assert(mode("rdinit=/r36-init androidboot.force_normal_boot=1 androidboot.mode=recovery",rc,1));assert(mode("rdinit=/r36-init androidboot.force_normal_boot=1 androidboot.force_normal_boot=1",rc,1));assert(mode("rdinit=/r36-init androidboot.force_normal_boot=2",rc,0));assert(mode("rdinit=/r36-init androidboot.force_normal_boot=1","androidboot.init_rc = \"/vendor_dlkm/r32/init.rc\"\nandroidboot.force_normal_boot = \"1\"\n",1));assert(mode("rdinit=/r36-init androidboot.mode=normal",rc,1));assert(mode("rdinit=/r36-init androidboot.bootmode=charger",rc,1));}
static void test_held_success(void){struct state s;reset(&s);events();assert(!reanchor_report(&s));assert(s.report_moved&&moved&&!original&&!s.report_original&&s.report_order_verified);assert(root_unmounts==1&&fd_place[reportfd]==2&&!fd_place[900]);assert(!retained_mounts(&s));assert(opens==2&&pins==3);assert(closes==8);for(int i=0;i<2;i++)assert(s.loop[i]==-1&&s.img[i]==-1&&s.owned[i]&&s.mounted[i]);assert(s.ctl==-1);assert(!private_cleanup(&s));assert(unmounts==3&&mounted[0]&&mounted[1]);if(!setjmp(executed)){handoff(&s,0);assert(0);}assert(execs==1&&!strstr(output,"event=cleanup_verified"));assert(strstr(output,"event=handoff_mounted"));save("native-mock-normal.log");}
static void failed_before_unmount(struct state *s){assert(reanchor_report(s));assert(!s->report_order_verified);assert(native_failure(s,EIO));assert(!execs);}
static void test_failures(void){struct state s;
 reset(&s);events();fail_bind=1;failed_before_unmount(&s);assert(!moved&&!mounted[0]&&!mounted[1]);
 for(int fault=1;fault<=4;fault++){reset(&s);events();bad_fstat=fault;failed_before_unmount(&s);assert(!moved&&original&&held_unmounts==1&&!mounted[1]);}
 reset(&s);events();bad_held_fs=1;assert(reanchor_report(&s)&&moved&&original);bad_held_fs=0;assert(native_failure(&s,EIO));assert(!execs&&!moved&&!mounted[1]);
 reset(&s);events();bad_held_flags=1;assert(reanchor_report(&s)&&moved&&original);bad_held_flags=0;assert(native_failure(&s,EIO));assert(!execs&&!moved&&!mounted[1]);
 reset(&s);events();assert(!reanchor_report(&s));fail_umount_at=2;assert(native_failure(&s,EIO));assert(!execs&&mounted[1]&&!moved&&strstr(output,"event=cleanup_failed")&&!strstr(output,"event=cleanup_verified"));

 reset(&s);events();bad_report=1;assert(reanchor_report(&s));bad_report=0;assert(native_failure(&s,EIO));assert(!execs&&!moved&&!mounted[0]&&!mounted[1]);
 reset(&s);events();fail_report_open=1;failed_before_unmount(&s);assert(!moved&&original&&held_unmounts==1&&!mounted[1]);
 reset(&s);events();fail_fstat=1;failed_before_unmount(&s);assert(!moved&&original&&held_unmounts==1&&!mounted[1]);
 reset(&s);events();fail_close=900;failed_before_unmount(&s);assert(!moved&&original&&!mounted[1]);
 reset(&s);events();fail_umount_at=1;failed_before_unmount(&s);assert(!moved&&original&&held_unmounts==1&&!mounted[1]);
 reset(&s);events();fail_order=1;failed_before_unmount(&s);assert(!moved&&original&&moves==1&&!mounted[1]);
 reset(&s);events();bad_order=1;failed_before_unmount(&s);assert(!moved&&original&&moves==1&&!mounted[1]);
 reset(&s);events();bad_parent=1;failed_before_unmount(&s);assert(!moved&&original&&moves==1&&!mounted[1]);
 reset(&s);events();assert(!reanchor_report(&s));fail_pin=1;assert(retained_mounts(&s));assert(native_failure(&s,EIO));assert(!execs&&!moved&&!mounted[0]&&!mounted[1]);assert(strstr(output,"event=report_returned")<strstr(output,"stage=cleanup-vendor-unmount"));assert(strstr(output,"event=cleanup_verified"));save("native-mock-failure-cleaned.log");
 reset(&s);events();assert(!reanchor_report(&s));fail_move=1;assert(native_failure(&s,EIO));assert(!execs&&moved&&unmounts==1&&mounted[1]);assert(!strstr(output,"event=cleanup_verified"));save("native-mock-report-return-failed.log");
 reset(&s);events();fail_umount_at=1;assert(reanchor_report(&s));fail_report_open=2;assert(native_failure(&s,EIO));assert(!execs&&original&&moved&&mounted[1]);
 reset(&s);events();fail_report_open=1;assert(reanchor_report(&s));fail_umount_at=1;assert(native_failure(&s,EIO));assert(!execs&&original&&moved&&mounted[1]);
 reset(&s);events();fail_report_open=1;assert(reanchor_report(&s));fail_close=900;assert(native_failure(&s,EIO));assert(!execs&&moved&&mounted[1]);
 reset(&s);events();assert(!reanchor_report(&s));bad_loop=1;assert(retained_mounts(&s));bad_loop=0;assert(native_failure(&s,EINVAL));assert(!execs);
 reset(&s);events();assert(!reanchor_report(&s));fail_close=11;assert(retained_mounts(&s));assert(!strstr(output,"event=helper_fds_closed"));assert(native_failure(&s,EIO));assert(!execs);
 reset(&s);events();assert(!reanchor_report(&s));fail_reopen=1;assert(retained_mounts(&s));fail_reopen=0;assert(native_failure(&s,ENOENT));assert(!execs);
 reset(&s);events();assert(!reanchor_report(&s));assert(!retained_mounts(&s));fail_umount_at=2;assert(private_cleanup(&s));assert(!strstr(output,"event=private_cleanup_verified"));assert(native_failure(&s,EIO));assert(!execs);
 reset(&s);events();assert(!reanchor_report(&s));assert(!retained_mounts(&s));assert(!private_cleanup(&s));fail_write=1;assert(handoff(&s,0));assert(!execs&&report_error);
 reset(&s);events();assert(!reanchor_report(&s));assert(!retained_mounts(&s));assert(!private_cleanup(&s));fail_close=reportfd;assert(handoff(&s,0));assert(!execs&&report_error);
 reset(&s);events();assert(!reanchor_report(&s));assert(cleanup(&s));assert(mounted[1]&&moved&&unmounts==1);
 reset(&s);events();assert(!reanchor_report(&s));s.report_order_verified=0;assert(handoff(&s,0));assert(!execs);
}
static void test_recovery_not_normal(void){struct state s;reset(&s);recovery_mode=1;mounted[0]=mounted[1]=0;s.mounted[0]=s.mounted[1]=s.owned[0]=s.owned[1]=s.sys=s.sys_touched=0;s.loop[0]=s.loop[1]=s.img[0]=s.img[1]=s.ctl=-1;stage="entry";event("start",0,"");stage="fixture";event("mode_verified",0,"mode=recovery selected_mode=recovery recovery_present=1 force_present=0 force_value=absent");event("recovery_identity_verified",0,"mode=recovery normal_android_mode_tested=0 init_sha256=%s recovery_sha256=%s rc_sha256=6631789e0a11de418bb33d0b82dc61638d5269ecb513b4090fd99cd3ed875112",R36_INIT_SHA256,recovery_hash);assert(!private_cleanup(&s));if(!setjmp(executed)){handoff(&s,1);assert(0);}assert(execs==1&&!strstr(output,"handoff_mounted")&&!moves&&!pins&&!opens);save("native-mock-recovery.log");}
static void test_actual_sha(void){struct state s;reset(&s);struct sha h;char hex[65];sha_init(&h);sha_add(&h,"abc",3);sha_end(&h,hex);assert(!strcmp(hex,"ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"));FILE*f=tmpfile();assert(f);assert(fwrite("abc",1,3,f)==3&&!fflush(f)&&!fchmod(fileno(f),0600));rewind(f);assert(!hash_fd(fileno(f),3,hex,0));assert(hash_fd(fileno(f),3,"aa7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",0));fclose(f);}
static int table(const char *input,int info,struct state *s){char copy[8192];assert(strlen(input)<sizeof(copy));strcpy(copy,input);return parse_report_order(copy,info,s);}
static void test_order_parser(void){struct state s;reset(&s);
 /* IDs can be recycled and need not increase with namespace row order. */
 const char *good="77 99 0:2 / / rw - rootfs rootfs rw\n300 77 7:0 / /system_dlkm ro - ext4 loop0 ro\n91 77 7:8 / /vendor_dlkm ro - ext4 loop1 ro\n2 91 0:50 / /vendor_dlkm/r36-report rw shared:42 - tmpfs tmpfs rw\n";
 assert(!table(good,1,&s));
 assert(table("4 1 7:0 / /system_dlkm ro - ext4 loop0 ro\n5 1 7:8 / /vendor_dlkm ro - ext4 loop1 ro\n6 5 0:50 / /vendor_dlkm/r36-report rw - tmpfs tmpfs rw\n2 1 0:50 / /r36-report rw - tmpfs tmpfs rw\n",1,&s));
 assert(table("4 1 7:0 / /system_dlkm ro - ext4 loop0 ro\n5 1 7:8 / /vendor_dlkm ro - ext4 loop1 ro\n6 1 0:50 / /vendor_dlkm/r36-report rw - tmpfs tmpfs rw\n",1,&s));
 assert(table("4 1 7:0 / /system_dlkm ro - ext4 loop0 ro\n5 1 7:8 / /vendor_dlkm ro - ext4 loop1 ro\n6 5 0:51 / /vendor_dlkm/r36-report rw - tmpfs tmpfs rw\n",1,&s));
 assert(table("4 1 7:0 / /system_dlkm ro - ext4 loop0 ro\n5 1 7:8 / /vendor_dlkm ro - ext4 loop1 ro\n6 5 0:50 / /vendor_dlkm/r36-report rw - ext4 tmpfs rw\n",1,&s));
 const char *mt="loop0 /system_dlkm ext4 ro 0 0\nloop1 /vendor_dlkm ext4 ro 0 0\ntmpfs /vendor_dlkm/r36-report tmpfs rw 0 0\n";
 assert(!table(mt,0,&s));
 assert(table("tmpfs /vendor_dlkm/r36-report tmpfs rw 0 0\nloop0 /system_dlkm ext4 ro 0 0\nloop1 /vendor_dlkm ext4 ro 0 0\n",0,&s));
 assert(table("loop0 /system_dlkm ext4 ro 0 0\nloop1 /vendor_dlkm ext4 ro 0 0\nloop2 /vendor_dlkm ext4 ro 0 0\ntmpfs /vendor_dlkm/r36-report tmpfs rw 0 0\n",0,&s));
 assert(table("loop0 /system_dlkm ext4 ro 0 0\nloop1 /vendor_dlkm ext4 ro 0 0\n",0,&s));
 assert(table("short row\n",0,&s));
}
int main(void){test_modes();test_actual_sha();test_order_parser();test_held_success();test_failures();test_recovery_not_normal();puts("PASS: mode boundaries; actual SHA; new nonrecursive bind + original removal; both mount table order gates, recycled IDs, stale source, duplicate/missing mounts, wrong parent/device/fs, malformed rows; all helper FDs closed before same-loop retained verification; both markers; only private mounts removed; normal handoff; failure report-return-before-unmount; partial-bind rollback + moveback failure no parent unmount; bad backing/pin/reopen/close/write block normal handoff; recovery is separate.");return 0;}
