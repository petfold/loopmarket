// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// The announcement channel (docs/plans/P1-federated-book.md §4, decided
// 2026-09-14): a maker says "my book is `book`" in one transaction, and
// anyone reads the announced set from the log. `msg.sender` is the owner
// — the same secp256k1 key that signs the maker's Swarm feed — so the
// announcement authenticates the book it names (U8's primary layer).
// `book` is a book spec without its owner (`swarm:TOPIC`); a reader
// opens `swarm:TOPIC@OWNER`. `role` is 0 for a maker, 1 for a clearing
// instance. The latest announcement per owner stands; `retract` ends it.
contract LoopBookRegistry {
    event Announce(address indexed owner, string book, uint8 role);
    event Retract(address indexed owner);

    function announce(string calldata book, uint8 role) external {
        emit Announce(msg.sender, book, role);
    }

    function retract() external {
        emit Retract(msg.sender);
    }
}
