//! Block identifier type and generator.
//!
//! `BlockId` is currently a `u64` alias to keep all external call sites
//! compiling. A future PR may newtype it once the shape is stable.

/// Stable identifier for a block. Monotonically increasing within a session.
pub type BlockId = u64;

/// Generates monotonically increasing block ids starting at 1.
#[derive(Debug, Clone)]
pub struct BlockIdGenerator {
    next: u64,
}

impl BlockIdGenerator {
    /// New generator starting at 1.
    pub const fn new() -> Self {
        Self { next: 1 }
    }

    /// Generator that resumes after the highest id seen so far.
    pub const fn after(highest: BlockId) -> Self {
        Self { next: highest + 1 }
    }

    /// Mint the next id.
    pub fn next_id(&mut self) -> BlockId {
        let id = self.next;
        self.next += 1;
        id
    }

    /// Peek the next id without consuming it.
    pub const fn peek(&self) -> BlockId {
        self.next
    }
}

impl Default for BlockIdGenerator {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ids_start_at_one() {
        let mut g = BlockIdGenerator::new();
        assert_eq!(g.next_id(), 1);
        assert_eq!(g.next_id(), 2);
    }

    #[test]
    fn after_resumes_above_highest() {
        let mut g = BlockIdGenerator::after(7);
        assert_eq!(g.next_id(), 8);
    }

    #[test]
    fn peek_does_not_consume() {
        let g = BlockIdGenerator::new();
        assert_eq!(g.peek(), 1);
        assert_eq!(g.peek(), 1);
    }
}
