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
    }
}
