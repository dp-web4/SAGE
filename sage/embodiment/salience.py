#!/usr/bin/env python3
"""Salience filtering — the high-bandwidth perceptual stream is mostly redundant;
only a tiny fraction is signal. This extracts it, SNARC-style, so that what reaches
the being's context (its journal, its raising digest) is the salient fraction, not
the raw torrent. For a mind whose identity lives in context, the filter *is* the
sensory curriculum.

SNARC-lite over the perceptual state:
  - Surprise  : prediction error vs a running expectation (EMA) of the stream.
  - Novelty   : 1 - habituation. Repeated event-signatures fade; new ones stand out.
  - Arousal   : raw intensity (motion + rotation rate).
  - Conflict  : reafference disagreement — vision says the world moved AND the IMU
                says I moved, so the cause is ambiguous. (Falls out of embodiment.)
  - Reward    : deferred (no goals yet).

A moment is "salient" when the blended score clears a threshold. Habituation means
88 near-identical "I was handled" events collapse to a couple of salient ones plus
a fade to normal — not 88 signals.
"""
from __future__ import annotations


class SalienceFilter:
    def __init__(self, threshold: float = 0.35):
        self.threshold = threshold
        self.exp_motion = 0.0    # expected max motion (EMA)
        self.exp_self = 0.0      # expected self-motion presence (EMA of 0/1)
        self.exp_trust = 0.85    # expected view quality (EMA)
        self.hab: dict = {}      # event-signature -> habituation level (0..1)
        self.obj_hab: dict = {}  # object-label -> habituation (0..1): a new THING is surprising,
                                 # a lingering one fades to normal, one that leaves is new again later

    def score(self, state: dict) -> dict:
        # Vision is one sense among three, not the precondition for the other two. Indexing
        # cams["0"]["motion"] directly made hearing and the inner ear unscoreable whenever an
        # eye was missing — which is how a dead camera silenced a whole organ on Sprout
        # (2026-09-14..17). A machine with no cameras at all scores on what it does have.
        cams = state.get("cameras") or {}
        eyes = [c for c in cams.values() if isinstance(c, dict)]
        prop = state.get("proprioception", {})
        # A stalled eye reports no motion because it reports nothing; it must not be read as
        # a confident observation of stillness, so only live eyes contribute motion.
        live = [c for c in eyes if not c.get("stalled")]
        motion = max((c.get("motion", 0.0) for c in live), default=0.0)
        self_mot = 1.0 if prop.get("self_motion") in ("moving", "rotating") else 0.0
        # With no live eye there is no view to judge: hold trust at the current expectation
        # so blindness does not masquerade as a permanent quality collapse. The eyes going
        # dark is surprising once (via the liveness term downstream), not surprising forever.
        trust = min((c.get("trust", 0.0) for c in live), default=self.exp_trust)
        gyro = prop.get("gyro_mag", 0.0)
        aud = state.get("audio", {})
        audio_onset = 1.0 if aud.get("onset") else 0.0
        audio_level = aud.get("level", 0.0)

        # Object-grounded salience: a NEW named thing entering the shared field is a strong
        # event — "a person appeared", not just "pixels changed". Union of confirmed objects
        # across both eyes; a label is "new" until it habituates; it fades when it leaves.
        objs = {o["label"] for c in eyes for o in (c.get("objects") or [])}
        new_objs = sorted(o for o in objs if self.obj_hab.get(o, 0.0) < 0.25)
        obj_surprise = 0.7 if new_objs else 0.0

        # Surprise: how far the moment departs from expectation — a sudden sound is surprising too,
        # and a newly-arrived object most of all.
        surprise = min(1.0, abs(motion - self.exp_motion)
                            + abs(self_mot - self.exp_self)
                            + max(0.0, self.exp_trust - trust)
                            + 0.4 * audio_onset
                            + obj_surprise)
        # Conflict: reafference ambiguity — visual change AND self-motion at once.
        conflict = 1.0 if (self_mot > 0.5 and motion > 0.15) else 0.0
        # Arousal: raw intensity — motion, rotation, and loudness.
        arousal = min(1.0, motion + gyro / 120.0 + audio_level)
        # Novelty via habituation on a coarse signature — the objects present are part of the
        # signature, so a change in WHAT is seen is a novel configuration (a sound is its own too).
        sig = (motion > 0.15, prop.get("self_motion", "?"),
               "clear" if trust > 0.6 else "murky", audio_onset > 0, tuple(sorted(objs)))
        h = self.hab.get(sig, 0.0)
        novelty = 1.0 - h

        # Blend → salience. Novelty gates arousal (an intense-but-familiar moment is
        # not salient); surprise and conflict contribute directly.
        salience = min(1.0, 0.45 * surprise + 0.30 * (novelty * arousal) + 0.25 * conflict)
        # A NEW named thing entering the field is inherently salient — floor it above the wake
        # bar so an engaged being reliably notices it even in an otherwise-still scene. (Still
        # below the resting bar 0.70, so a chosen rest isn't broken by every passing object.)
        if new_objs:
            salience = max(salience, 0.55)

        # Update state: habituate this signature, slowly forget the rest, track expectations.
        for k in list(self.hab):
            self.hab[k] *= 0.985
        self.hab[sig] = min(1.0, h + 0.12)
        # Object habituation: present objects habituate (~1s to stop being "new"); absent ones
        # fade (~gone after ~15s → new again if they return). Drop fully-forgotten labels.
        for k in list(self.obj_hab):
            self.obj_hab[k] *= 0.97
            if self.obj_hab[k] < 0.02:
                del self.obj_hab[k]
        for o in objs:
            self.obj_hab[o] = min(1.0, self.obj_hab.get(o, 0.0) + 0.08)
        self.exp_motion = 0.9 * self.exp_motion + 0.1 * motion
        self.exp_self = 0.9 * self.exp_self + 0.1 * self_mot
        self.exp_trust = 0.9 * self.exp_trust + 0.1 * trust

        out = {
            "salience": round(salience, 3),
            "salient": salience >= self.threshold,
            "surprise": round(surprise, 3),
            "novelty": round(novelty, 3),
            "arousal": round(arousal, 3),
            "conflict": conflict,
        }
        if new_objs:
            out["new_objects"] = new_objs   # what newly entered the field this moment
        return out
