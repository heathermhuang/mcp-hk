/** Candidate data is already saved in R2. Its container must independently
 * download/restore/compare that exact checkpoint before publication can advance. */
export async function completeRacingPublication<T extends {sha256:string}>(
  response: Response,
  receipt: T,
  qualify: (version:string,digest:string)=>Promise<Response>,
  save: (accepted:Response)=>Promise<T>,
) {
  const version=response.headers.get('X-Racing-Candidate');
  if(!version)return receipt;
  if(!/^racing-(?:results|profile)-v1-[a-f0-9]{64}$/.test(version))throw new Error('RACING_CANDIDATE_INVALID');
  const accepted=await qualify(version,receipt.sha256);
  if(!accepted.ok){await accepted.body?.cancel();throw new Error('RACING_OFFSITE_RESTORE_NOT_CONFIRMED');}
  return {...await save(accepted),racing:{version,restoreCheckpointSha256:receipt.sha256}};
}
