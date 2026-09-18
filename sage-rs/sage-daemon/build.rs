//! Stamp the build so a running daemon can say which one it is (SAGE #111 finding 6).
//!
//! `version` has read "0.1.0" since Sprint 1 and `/status` carried a hard-coded sprint label,
//! so a daemon built months ago and one built minutes ago answered identically. dp read a
//! current binary as "quite old" on exactly that evidence, and was right to.
//!
//! Emits `SAGE_BUILD` = `<version>+<git sha><-dirty>@<UTC date>`. Never fails the build: a
//! source tree with no git (a release tarball) stamps `+nogit`, which is still more than
//! nothing.
use std::process::Command;

fn main() {
    let sha = Command::new("git")
        .args(["rev-parse", "--short=9", "HEAD"])
        .output()
        .ok()
        .filter(|o| o.status.success())
        .map(|o| String::from_utf8_lossy(&o.stdout).trim().to_string())
        .unwrap_or_else(|| "nogit".to_string());

    // Scoped to the daemon's own sources, NOT the whole repo. Unscoped, this flag was stuck
    // on forever: the beings rewrite their instance directories every beat, so `-dirty` said
    // "a being has been living here" rather than "this binary differs from its commit", which
    // is the only thing a reader can act on. Measured 2026-09-18: a tree with zero source
    // changes stamped `-dirty` regardless.
    let dirty = Command::new("git")
        .args(["status", "--porcelain", "--untracked-files=no", "--", "."])
        .output()
        .ok()
        .filter(|o| o.status.success())
        .map(|o| !o.stdout.is_empty())
        .unwrap_or(false);

    let date = Command::new("date")
        .args(["-u", "+%Y-%m-%dT%H:%MZ"])
        .output()
        .ok()
        .map(|o| String::from_utf8_lossy(&o.stdout).trim().to_string())
        .unwrap_or_default();

    println!(
        "cargo:rustc-env=SAGE_BUILD={}+{}{}@{}",
        env!("CARGO_PKG_VERSION"),
        sha,
        if dirty { "-dirty" } else { "" },
        date
    );
    // Restamp when HEAD moves, not only when a source file changes.
    println!("cargo:rerun-if-changed=../.git/HEAD");
    println!("cargo:rerun-if-changed=build.rs");
}
