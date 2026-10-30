#include <stddef.h>
#include <stdio.h>
#include <errno.h>
#include <unistd.h>
#include <sys/prctl.h>
#include <linux/filter.h>
#include <linux/seccomp.h>
#include <linux/audit.h>
/* Docker <20.10.10 rejects clone3 with EPERM. Return ENOSYS so libc uses
 * the existing clone syscall. This adds a denial; existing filters remain. */
int main(int argc, char **argv) {
  if (argc < 2) { fputs("usage: paseo-compat command [args]\n", stderr); return 2; }
  struct sock_filter rules[] = {
    BPF_STMT(BPF_LD|BPF_W|BPF_ABS, offsetof(struct seccomp_data, arch)),
    BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K, AUDIT_ARCH_X86_64, 1, 0),
    BPF_STMT(BPF_RET|BPF_K, SECCOMP_RET_KILL_PROCESS),
    BPF_STMT(BPF_LD|BPF_W|BPF_ABS, offsetof(struct seccomp_data, nr)),
    BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K, 435, 0, 1),
    BPF_STMT(BPF_RET|BPF_K, SECCOMP_RET_ERRNO | ENOSYS),
    BPF_STMT(BPF_RET|BPF_K, SECCOMP_RET_ALLOW)
  };
  struct sock_fprog program = {sizeof(rules)/sizeof(rules[0]), rules};
  if (prctl(PR_SET_NO_NEW_PRIVS,1,0,0,0) || prctl(PR_SET_SECCOMP,SECCOMP_MODE_FILTER,&program)) { perror("seccomp compatibility"); return 126; }
  execvp(argv[1], &argv[1]); perror("exec"); return 127;
}
