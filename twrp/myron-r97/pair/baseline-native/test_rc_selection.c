#define R36_UNIT_TEST
#include "r36_init.c"
#include <assert.h>
int main(void){
 assert(!select_recovery_rc_size(5341));assert(recovery_rc_bytes==5341);assert(!strcmp(recovery_rc_hash,"6631789e0a11de418bb33d0b82dc61638d5269ecb513b4090fd99cd3ed875112"));
 assert(!select_recovery_rc_size(10292));assert(recovery_rc_bytes==10292);assert(!strcmp(recovery_rc_hash,"e04e4323eb7b18e000f4bc227510b18ac86fa5e931502aed77f34150f15a5424"));
 assert(select_recovery_rc_size(0));assert(select_recovery_rc_size(5340));assert(select_recovery_rc_size(10292+1));assert(select_recovery_rc_size(UINT64_MAX));
 assert(!select_recovery_rc_size(5341));assert(!strcmp(recovery_rc_hash,"6631789e0a11de418bb33d0b82dc61638d5269ecb513b4090fd99cd3ed875112"));
 puts("PASS legacy/R95 RC selection and unknown-size rejection");return 0;
}
