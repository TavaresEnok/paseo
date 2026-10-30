import { compare } from "bcryptjs";
import { OWNER_PERMISSIONS } from "./authorization/index.js";
import { matchesLocalCredential } from "./local-credential.js";
export async function resolveSessionAdmission(input) {
    const { credential, passwordHash, localCredential } = input;
    if (!passwordHash) {
        return { admission: { principalId: "owner", permissions: OWNER_PERMISSIONS } };
    }
    if (!credential) {
        return { rejection: "password_required" };
    }
    if (credential.kind === "localCredential") {
        if (localCredential && matchesLocalCredential(localCredential, credential.token)) {
            return { admission: { principalId: "owner", permissions: OWNER_PERMISSIONS } };
        }
        return { rejection: "incorrect_password" };
    }
    return (await compare(credential.password, passwordHash))
        ? { admission: { principalId: "owner", permissions: OWNER_PERMISSIONS } }
        : { rejection: "incorrect_password" };
}
//# sourceMappingURL=session-admission-auth.js.map