--------------------------- MODULE Attempts ---------------------------
EXTENDS Naturals, FiniteSets
CONSTANTS MaxAttempts, BrokenAttemptGuard, BrokenRecovery, BrokenTerminalGuard
VARIABLES status, attempt, lease, observed, committed, writerAttempt, validCommit, wasCompleted
vars == <<status, attempt, lease, observed, committed, writerAttempt, validCommit, wasCompleted>>
Init == /\ status = "queued" /\ attempt = 0 /\ lease = FALSE
        /\ observed = 0 /\ committed = FALSE /\ writerAttempt = 0
        /\ validCommit = TRUE /\ wasCompleted = FALSE
Claim == /\ status = "queued" /\ attempt < MaxAttempts
         /\ status' = "running" /\ attempt' = attempt + 1 /\ lease' = TRUE
         /\ UNCHANGED <<observed, committed, writerAttempt, validCommit, wasCompleted>>
Expire == /\ status = "running" /\ lease /\ lease' = FALSE
          /\ UNCHANGED <<status, attempt, observed, committed, writerAttempt, validCommit, wasCompleted>>
Heartbeat == /\ status = "running" /\ lease /\ UNCHANGED vars
Scan == /\ status = "running" /\ ~lease /\ observed' = attempt
        /\ UNCHANGED <<status, attempt, lease, committed, writerAttempt, validCommit, wasCompleted>>
Recover == /\ ~BrokenRecovery /\ status = "running" /\ ~lease /\ observed = attempt
           /\ status' = "queued" /\ observed' = 0
           /\ UNCHANGED <<attempt, lease, committed, writerAttempt, validCommit, wasCompleted>>
Commit(a) == /\ status = "running" /\ lease /\ a \in 1..attempt
             /\ (BrokenAttemptGuard \/ a = attempt)
             /\ committed' = TRUE /\ writerAttempt' = a
             /\ validCommit' = (a = attempt)
             /\ UNCHANGED <<status, attempt, lease, observed, wasCompleted>>
Complete == /\ status = "running" /\ lease /\ committed /\ writerAttempt = attempt
            /\ status' = "completed" /\ lease' = FALSE /\ wasCompleted' = TRUE
            /\ UNCHANGED <<attempt, observed, committed, writerAttempt, validCommit>>
LateFail == /\ BrokenTerminalGuard /\ status = "completed" /\ status' = "failed"
            /\ UNCHANGED <<attempt, lease, observed, committed, writerAttempt, validCommit, wasCompleted>>
Done == /\ status \in {"completed", "failed"} /\ UNCHANGED vars
Next == Claim \/ Expire \/ Heartbeat \/ Scan \/ Recover \/ (\E a \in 1..MaxAttempts: Commit(a)) \/ Complete \/ LateFail \/ Done
Spec == Init /\ [][Next]_vars /\ WF_vars(Scan) /\ WF_vars(Recover)
TypeOK == /\ status \in {"queued", "running", "completed", "failed"}
          /\ attempt \in 0..MaxAttempts /\ lease \in BOOLEAN
OnlyCurrentAttemptCommits == validCommit
CompletedDoesNotRegress == wasCompleted => status = "completed"
ExpiredEventuallyLeavesRunning == (status = "running" /\ ~lease) ~> (status # "running")
=============================================================================
