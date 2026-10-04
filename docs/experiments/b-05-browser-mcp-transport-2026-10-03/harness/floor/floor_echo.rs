//! B-05 stdio floor server (FIXTURE, measurement only). Standard library only.
//!
//!   floor_echo <frames.bin> <stamps.txt>
//!
//! Replays recorded Driver response frames, byte for byte, in request order. frames.bin is a
//! sequence of records `[u32 LE req_len][req bytes][u32 LE resp_len | 0xFFFFFFFF = no response]
//! [resp bytes]`. For every newline-terminated line read from stdin (the MCP client's request), the
//! server compares it with the next recorded request, then writes the paired recorded response plus
//! `\n` with one write(2) on fd 1 (no buffering, no parsing, no JSON work). CLOCK_MONOTONIC stamps
//! (line read complete, response written) are kept in memory and written to stamps.txt at EOF, so
//! the server does no file I/O between requests.

use std::fs::File;
use std::io::{BufRead, BufReader, Write};
use std::os::unix::io::FromRawFd;

#[repr(C)]
struct Timespec {
    tv_sec: i64,
    tv_nsec: i64,
}

extern "C" {
    fn clock_gettime(clk_id: i32, tp: *mut Timespec) -> i32;
}

const CLOCK_MONOTONIC: i32 = 1;

fn mono_ns() -> u64 {
    let mut ts = Timespec { tv_sec: 0, tv_nsec: 0 };
    // SAFETY: valid pointer to a writable timespec; CLOCK_MONOTONIC exists on Linux.
    unsafe { clock_gettime(CLOCK_MONOTONIC, &mut ts) };
    (ts.tv_sec as u64) * 1_000_000_000 + ts.tv_nsec as u64
}

fn read_u32(data: &[u8], at: &mut usize) -> u32 {
    let v = u32::from_le_bytes([data[*at], data[*at + 1], data[*at + 2], data[*at + 3]]);
    *at += 4;
    v
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let data = std::fs::read(&args[1]).expect("frames file");
    let mut pairs: Vec<(Vec<u8>, Option<Vec<u8>>)> = Vec::new();
    let mut at = 0usize;
    while at < data.len() {
        let rl = read_u32(&data, &mut at) as usize;
        let req = data[at..at + rl].to_vec();
        at += rl;
        let sl = read_u32(&data, &mut at);
        let resp = if sl == u32::MAX {
            None
        } else {
            let mut frame = data[at..at + sl as usize].to_vec();
            at += sl as usize;
            frame.push(b'\n');
            Some(frame)
        };
        pairs.push((req, resp));
    }
    // SAFETY: fds 0 and 1 are the pipes the MCP client opened for this process; owned here.
    let stdin = unsafe { File::from_raw_fd(0) };
    let mut stdout = unsafe { File::from_raw_fd(1) };
    let mut reader = BufReader::new(stdin);
    let mut stamps: Vec<(usize, u64, u64, bool, usize)> = Vec::with_capacity(pairs.len());
    let mut line: Vec<u8> = Vec::with_capacity(1 << 16);
    let mut idx = 0usize;
    loop {
        line.clear();
        let n = reader.read_until(b'\n', &mut line).unwrap_or(0);
        if n == 0 {
            break;
        }
        let t_read = mono_ns();
        if line.last() == Some(&b'\n') {
            line.pop();
        }
        if idx >= pairs.len() {
            stamps.push((idx, t_read, t_read, false, 0));
            idx += 1;
            continue;
        }
        let matched = line == pairs[idx].0;
        let mut len = 0usize;
        if let Some(frame) = &pairs[idx].1 {
            stdout.write_all(frame).expect("write response");
            len = frame.len();
        }
        let t_written = mono_ns();
        stamps.push((idx, t_read, t_written, matched, len));
        idx += 1;
    }
    let mut out = String::new();
    for (i, r, w, m, l) in stamps {
        out.push_str(&format!("{i} {r} {w} {} {l}\n", if m { 1 } else { 0 }));
    }
    std::fs::write(&args[2], out).expect("stamps file");
}
