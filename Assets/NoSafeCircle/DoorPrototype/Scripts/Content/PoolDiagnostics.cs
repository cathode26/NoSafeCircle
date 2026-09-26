using System;

namespace NoSafeCircle.DoorPrototype.Content
{
    /// <summary>
    /// What a pool counts about itself. ENGINEERING_STANDARDS 9.4, one counter per line of the standard.
    /// </summary>
    /// <remarks>
    /// These are counted in every build, not only development ones: the cost is an integer increment on
    /// paths that are already doing an Instantiate or a HashSet lookup, and a counter that only exists
    /// in the Editor is a counter nobody reads from a WebGL player's console. Reading them is free;
    /// mutating them is the pool's alone.
    /// </remarks>
    public sealed class PoolDiagnostics
    {
        /// <summary>An instance returned while already idle in the pool.</summary>
        public int DoubleReturns { get; internal set; }

        /// <summary>An instance returned that this pool never created.</summary>
        public int ForeignReturns { get; internal set; }

        /// <summary>An instance handed out while already checked out. A pool bug, not a caller bug.</summary>
        public int DoubleCheckouts { get; internal set; }

        /// <summary>Instances still checked out when the pool was disposed.</summary>
        public int ActiveAtDisposal { get; internal set; }

        /// <summary>Instances created beyond the initial capacity.</summary>
        public int Expansions { get; internal set; }

        /// <summary>Checkouts refused at maximum capacity under <see cref="PoolOverflowPolicy.Reject"/>.</summary>
        public int RejectedRequests { get; internal set; }

        /// <summary>The most instances checked out at once.</summary>
        public int PeakActive { get; internal set; }

        /// <summary>True when any counter that indicates misuse is non-zero.</summary>
        public bool HasAnomaly =>
            DoubleReturns > 0 || ForeignReturns > 0 || DoubleCheckouts > 0 || ActiveAtDisposal > 0;

        internal void RecordActive(int activeCount)
        {
            PeakActive = Math.Max(PeakActive, activeCount);
        }

        /// <summary>A return the pool refused: of an instance already idle, or of one it never made.</summary>
        internal void RecordMisreturn(bool wasAlreadyIdle)
        {
            if (wasAlreadyIdle)
            {
                DoubleReturns++;
            }
            else
            {
                ForeignReturns++;
            }
        }

        /// <summary>One line, for a log or a test failure message.</summary>
        public string Report(string poolName) =>
            "Pool '" + poolName + "': peak active " + PeakActive + ", expansions " + Expansions
            + ", rejected " + RejectedRequests + ", double returns " + DoubleReturns
            + ", foreign returns " + ForeignReturns + ", double checkouts " + DoubleCheckouts
            + ", active at disposal " + ActiveAtDisposal + ".";
    }
}
