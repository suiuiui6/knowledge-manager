export const title = '任务执行尝试与租约恢复';
export const state = v => v.status === 'running' ? (v.lease ? '当前尝试运行中' : '租约已过期') : ({queued:'等待领取',completed:'结果已完成',failed:'失败终态'}[v.status]);
export const step = action => ({Claim:'领取新尝试',Expire:'租约到期',Recover:'原子回收',Complete:'提交完成',LateFail:'迟到失败改写终态',Scan:'发现过期任务',Commit:'提交本地结果',Done:'保持终态',Heartbeat:'续租'})[action] || action;
