/* Host substitutions for hardware I/O only; production parser/show executes. */
typedef uint8_t u8;
typedef uint16_t u16;
#define pr_debug(...) ((void)0)
#define MIPI_DSI_MSG_USE_LPM (1U << 1)
#define MIPI_DSI_MSG_UNICAST_COMMAND (1U << 7)
#define MIPI_DSI_MSG_BATCH_COMMAND (1U << 6)
#define DSI_CTRL_CMD_READ (1U << 7)
#define DSI_CORE_CLK 1
#define DSI_LINK_CLK 2
#define DSI_CLK_ON 1
#define DSI_CLK_OFF 0
#define MAX_DSI_CTRLS_PER_DISPLAY 2
static int mutex_trylock(struct mutex *m) { if(m->locked)return 0; mutex_lock(m);return 1; }
struct property { const char *name; const void *data; int size; };
struct device_node { int present,count;u32 maximum; struct property *props;u32 nr; };
static struct property *prop_find(struct device_node *n,const char *s) { for(u32 i=0;i<n->nr;i++)if(!strcmp(n->props[i].name,s))return &n->props[i];return NULL; }
static void *of_find_property(struct device_node *n,const char *s,void *unused) { if(!strcmp(s,"mi,max-brightness-clone"))return n->present?n:NULL;return prop_find(n,s); }
static const void *of_get_property(struct device_node *n,const char *s,int *len) { struct property*p=prop_find(n,s);if(!p)return NULL;if(len)*len=p->size;return p->data; }
static int of_property_count_u32_elems(struct device_node*n,const char*s) { struct property*p;if(!strcmp(s,"mi,max-brightness-clone"))return n->count;p=prop_find(n,s);return !p?-EINVAL:p->size%4?-EINVAL:p->size/4; }
static int of_property_read_u32(struct device_node*n,const char*s,u32*v) { *v=n->maximum;return 0; }
static int of_property_read_u32_array(struct device_node*n,const char*s,u32*v,size_t count) { struct property*p=prop_find(n,s);if(!p||p->size!=(int)(count*4))return -EINVAL;memcpy(v,p->data,count*4);return 0; }
static int of_property_read_string(struct device_node*n,const char*s,const char**v) { struct property*p=prop_find(n,s);if(!p)return -EINVAL;if(!p->size||!memchr(p->data,0,p->size))return -EILSEQ;*v=p->data;return 0; }
struct dsi_panel { struct device_node*panel_of_node;const char*name;struct mutex lock;bool panel_initialized;int esd_recovery_pending; };
struct platform_device { int unused; };
struct sde_vm { struct mutex vm_res_lock;bool owns; };
struct sde_kms { struct sde_vm*vm;bool suspended; };
struct drm_device { struct sde_kms*kms; };
struct dsi_ctrl { bool secure_mode; };
struct dsi_display_ctrl { struct dsi_ctrl*ctrl; };
struct mipi_dsi_host { int unused; };
struct dsi_display { struct dsi_panel*panel;struct device_node*panel_node;const char*display_type;struct platform_device*pdev;struct mutex display_lock;struct drm_device*drm_dev;struct dsi_display_ctrl ctrl[2];u32 cmd_master_idx,ctrl_count;void*dsi_clk_handle;struct mipi_dsi_host host;bool sim,bypass,host_ready;void*tx_cmd_buf; };
struct mipi_dsi_msg {u8 channel,type;u16 flags;size_t tx_len;const void*tx_buf;size_t rx_len;void*rx_buf;};
struct dsi_cmd_desc {struct mipi_dsi_msg msg;bool last_command;u32 post_wait_ms,ctrl,ctrl_flags;};
static int atomic_read(int*p){return *p;}
static struct sde_kms*ddev_to_msm_kms(struct drm_device*d){return d->kms;}
#define to_sde_kms(x) (x)
static bool sde_kms_is_suspend_blocked(struct drm_device*d){return d->kms->suspended;}
static bool sde_vm_owns_hw(struct sde_kms*k){return !k->vm||k->vm->owns;}
static void dsi_panel_acquire_panel_lock(struct dsi_panel*p){mutex_lock(&p->lock);}
static void dsi_panel_release_panel_lock(struct dsi_panel*p){mutex_unlock(&p->lock);}
static bool is_sim_panel(struct dsi_display*d){return d->sim;}
static bool phy_pll_bypass(struct dsi_display*d){return d->bypass;}
static int dsi_display_ctrl_get_host_init_state(struct dsi_display*d,bool*s){*s=d->host_ready;return 0;}
static struct dsi_display *active_display;
static int io_failure,clock_depth,prepare_depth,irq_depth,writes,reads;
static u8 read_bytes[256];
static unsigned int read_flags;
static char trace[512];static unsigned int trace_len;
static void step(char c){assert(trace_len<sizeof(trace)-1);trace[trace_len++]=c;trace[trace_len]=0;}
static void held(void){assert(active_display->display_lock.locked&&active_display->panel->lock.locked);}
static int dsi_display_wake_up(struct dsi_display*d){held();step('A');return io_failure==8?-EIO:0;}
static int dsi_host_alloc_cmd_tx_buffer(struct dsi_display*d){held();step('B');if(io_failure==9)return -ENOMEM;d->tx_cmd_buf=d;return 0;}
static int dsi_display_clk_ctrl(void*h,int type,int on){held();step(on?'C':'c');if(on){if(io_failure==1)return -EIO;assert(!clock_depth);clock_depth++;}else{assert(clock_depth==1);clock_depth--;if(io_failure==7)return -EIO;}return 0;}
static int dsi_host_transfer_sub(struct mipi_dsi_host*h,struct dsi_cmd_desc*c,bool flush){held();assert(clock_depth);writes++;step('W');assert(c->last_command&&c->msg.tx_len);if((io_failure==2&&writes==1)||(io_failure==6&&writes==2))return -EIO;return 0;}
static void usleep_range(unsigned long a,unsigned long b){held();assert(b==a+10);step('D');}
static void dsi_display_toggle_error_interrupt_status(struct dsi_display*d,bool enable){held();step(enable?'i':'I');if(enable){assert(irq_depth==1);irq_depth--;}else{assert(!irq_depth);irq_depth++;}}
static void dsi_display_set_cmd_tx_ctrl_flags(struct dsi_display*d,struct dsi_cmd_desc*c){held();assert(c->ctrl_flags==DSI_CTRL_CMD_READ);assert(c->msg.flags&MIPI_DSI_MSG_UNICAST_COMMAND);}
static int dsi_ctrl_transfer_prepare(struct dsi_ctrl*c,u32 f){held();step('P');if(io_failure==3)return -EIO;assert(!prepare_depth);prepare_depth++;return 0;}
static void dsi_ctrl_transfer_unprepare(struct dsi_ctrl*c,u32 f){held();step('U');assert(prepare_depth==1);prepare_depth--;}
static int dsi_ctrl_cmd_transfer(struct dsi_ctrl*c,struct dsi_cmd_desc*cmd,bool flush){held();step('R');assert(prepare_depth&&irq_depth&&clock_depth);reads++;read_flags=cmd->msg.flags;if(io_failure==4)return -EIO;memcpy(cmd->msg.rx_buf,read_bytes,cmd->msg.rx_len);return io_failure==5?(int)cmd->msg.rx_len-1:(int)cmd->msg.rx_len;}
