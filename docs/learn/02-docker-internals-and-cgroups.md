# Lesson 2: Docker internals, isolation and cgroups

**Code for this lesson:** `flakelab/runners.py` (DockerRunner), `flakelab/conditions.py`

## A. Fundamentals

A **container** is not a small virtual machine. It's an ordinary Linux process that the
kernel shows a restricted view of the system to. Two kernel features do almost all the work:

- **Namespaces** decide what a process can *see*: its own process list (PID namespace), its
  own network interfaces (network namespace), its own filesystem tree (mount namespace),
  its own hostname (UTS).
- **cgroups** (control groups) decide how much a process can *use*: CPU time, memory, I/O.

An **image** is a read-only stack of filesystem layers plus metadata (default command,
environment, labels). A container is an image plus a thin writable layer plus a running process.

## B. Theory: how FlakeLab's conditions work inside the kernel

**`--cpus 0.25`.** Docker writes a quota into the container's cgroup: `cpu.max = 25000 100000`.
The Completely Fair Scheduler lets the container's processes run for 25,000 µs in every
100,000 µs period, then throttles them until the next period. Work that needs 60 ms of CPU
therefore takes about 240 ms of wall time. That's why `test_authorize_within_sla` fails:
it measures *wall* time against a deadline.

**`--memory 128m --memory-swap 128m`.** The cgroup memory controller caps the container at
128 MB with no swap. When a process asks for more and nothing can be reclaimed, the kernel's
**OOM killer** picks a process in that cgroup (usually the one using the most memory) and
sends SIGKILL. Exit code -9. In the demo, the export runs in a child process, so the child
dies and pytest survives to report the failure.

**`--network none`.** The container gets a new network namespace with only a loopback
interface: no routes, no DNS. Any call to `weather-api` fails immediately.

**`TZ=IST-5:30`.** Not a kernel feature: the C library reads the `TZ` variable to convert
timestamps to local time. A POSIX TZ string works even in slim images that have no timezone
database.

## C. In our code

`DockerRunner.run()` does, for every run:
1. `docker create` with the condition's flags, environment variables and network,
2. `docker cp` the pytest plugin into the stopped container (works with any image),
3. `docker start -a` and wait, with a timeout,
4. `docker inspect` to read `OOMKilled`,
5. `docker cp` the results file out, then `docker rm -f`, always (`finally:`).

## D. Design decisions

- **Fresh container per run** keeps runs independent, which the statistics assume.
- **`docker cp` instead of rebuilding images** means FlakeLab needs no change to your project.
- **`finally: docker rm -f`** guarantees no leftover containers even when a run crashes.

## E. Alternatives

- **Virtual machines:** stronger isolation, but minutes to boot instead of under a second.
- **`ulimit` / `nice` without containers:** can't cut the network or cap CPU precisely.
- **Docker-in-Docker:** needs privileged mode; Docker-out-of-Docker (mounting the socket) is
  simpler, but gives root-equivalent access to the host.

## F. Performance

Each run pays container create/start/copy/remove overhead. FlakeLab measures it: run wall
time minus time inside pytest (see `timing.mean_overhead_seconds` in `results.json`).

## G. Edge cases and security

- OOM kill of pytest itself: the plugin writes results after every test, so the running
  test is marked `crashed`.
- A test that hangs: `docker start -a` has a timeout, then `docker kill`.
- Mounting `/var/run/docker.sock` = root on the host. Only on machines you control.

## H. Interview questions

1. What is the difference between an image and a container?
2. Which kernel feature limits CPU, and which one hides other processes?
3. Why can a container with `--cpus 0.25` still use 100% of one core for a short burst?
4. What does the OOM killer choose, and how does Docker know it happened?
5. Why is giving a container the Docker socket dangerous?

## I. Exercises

1. Run `docker run --rm --cpus 0.25 python:3.12-slim python -c "import time;s=time.time();sum(range(30_000_000));print(time.time()-s)"`,
   then without `--cpus`. Compare the times and explain the ratio.
2. Run `docker run --rm --network none python:3.12-slim python -c "import socket;print(socket.gethostbyname('github.com'))"`.
   What error do you get and why?
3. In `runners.py`, find where the container is removed. What would happen if that line were
   not in a `finally:` block and `docker start` timed out?
