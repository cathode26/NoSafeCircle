using System.IO;
using System;
using NoSafeCircle.DoorPrototype.Diagnostics;
using NUnit.Framework;

namespace NoSafeCircle.DoorPrototype.Tests.Editor
{
    /// <summary>
    /// Proves the one rule that decides whether the walkthrough readout corrupts its own
    /// evidence.
    /// </summary>
    /// <remarks>
    /// The capture is ScreenCapture.CaptureScreenshotIntoRenderTexture, which grabs the
    /// COMPOSED SCREEN rather than rendering a camera. So anything OnGUI draws during a
    /// captured frame is burned into that PNG, and no layer culling or camera mask can
    /// prevent it. The failure is silent: the run still writes three hundred plausible
    /// frames, the log still says it saved them, and only opening one shows a debug
    /// counter stamped across the room somebody is being asked to judge. It fails BY
    /// PRODUCING OUTPUT, which is the expensive kind.
    /// <para>
    /// The rule is therefore a pure function, so it can be proven by a table here instead
    /// of by looking at a screenshot afterwards.
    /// </para>
    /// </remarks>
    public sealed class WalkthroughOverlayTests
    {
        [Test]
        public void Recording_AndNotCapturingThisFrame_DrawsTheReadout()
        {
            Assert.IsTrue(WalkthroughCapture.ShouldDrawOverlay(
                isCapturing: true, summaryVisible: false, suppressedForCapture: false));
        }

        [Test]
        public void Recording_WhileCapturingThisFrame_IsSuppressed()
        {
            Assert.IsFalse(
                WalkthroughCapture.ShouldDrawOverlay(
                    isCapturing: true, summaryVisible: false, suppressedForCapture: true),
                "A readout drawn on a captured frame is burned into the PNG.");
        }

        [Test]
        public void Summary_AfterStopping_DrawsTheFinalCountAndPath()
        {
            Assert.IsTrue(WalkthroughCapture.ShouldDrawOverlay(
                isCapturing: false, summaryVisible: true, suppressedForCapture: false));
        }

        [Test]
        public void Summary_WhileCapturingThisFrame_IsAlsoSuppressed()
        {
            Assert.IsFalse(WalkthroughCapture.ShouldDrawOverlay(
                isCapturing: false, summaryVisible: true, suppressedForCapture: true));
        }

        [Test]
        public void Idle_DrawsNothing()
        {
            Assert.IsFalse(WalkthroughCapture.ShouldDrawOverlay(
                isCapturing: false, summaryVisible: false, suppressedForCapture: false));
        }

        /// <summary>
        /// Suppression wins over every other state, exhaustively rather than by example.
        /// </summary>
        [Test]
        public void Suppressed_DrawsNothing_WhateverElseIsTrue()
        {
            foreach (bool isCapturing in new[] { false, true })
            {
                foreach (bool summaryVisible in new[] { false, true })
                {
                    Assert.IsFalse(
                        WalkthroughCapture.ShouldDrawOverlay(
                            isCapturing, summaryVisible, suppressedForCapture: true),
                        "isCapturing=" + isCapturing + " summaryVisible=" + summaryVisible);
                }
            }
        }

        // U2 REGRESSION. The session stamp resolves to the SECOND and
        // Directory.CreateDirectory reports SUCCESS for a directory that already exists,
        // so two captures started in the same second used to share a directory: the
        // second restarted frame numbering at 000001 and overwrote the first session in
        // place, with no error. Break it on purpose -- ask for the SAME day and stamp
        // twice and require two different directories.
        [Test]
        public void SessionDirectory_IsNeverHandedOutTwiceForTheSameSecond()
        {
            string root = Path.Combine(
                Path.GetTempPath(), "nsc-walkthrough-dir-test-" + Guid.NewGuid().ToString("N"));
            try
            {
                const string day = "2026-09-23";
                const string stamp = "04_15_09";

                Assert.IsTrue(
                    WalkthroughCapture.TryCreateFreshDirectory(root, day, stamp, out string first),
                    "The first session must get a directory.");
                Assert.IsTrue(
                    WalkthroughCapture.TryCreateFreshDirectory(root, day, stamp, out string second),
                    "The second session must still get a directory.");

                Assert.AreNotEqual(first, second,
                    "Two captures in the same second must not share a directory: the second " +
                    "would overwrite the first session frame for frame.");
                Assert.IsTrue(Directory.Exists(first));
                Assert.IsTrue(Directory.Exists(second));

                // A third must not collide with either of the first two.
                Assert.IsTrue(
                    WalkthroughCapture.TryCreateFreshDirectory(root, day, stamp, out string third));
                Assert.AreNotEqual(first, third);
                Assert.AreNotEqual(second, third);
            }
            finally
            {
                if (Directory.Exists(root))
                {
                    Directory.Delete(root, true);
                }
            }
        }
    }
}
