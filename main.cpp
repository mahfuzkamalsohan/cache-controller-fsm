#include <iostream>
#include <queue>
#include <string>
#include <iomanip>
#include <cstdint>
using namespace std;

// Define Cache and Memory sizes
// 16 KB Direct-Mapped Cache with 16-byte blocks
// Blocks: 1024
// Index bits: 10 (log2(1024))
// Tag bits: (32 - 10 - 4) = 18 (assuming 4 bits for block offset)

// 1010 1011 1100 1101 0001 0010 0011 0100
// Tag: 1010 1011 1100 1101 00 (18 bits)
// Index: 01 0010 0011 (10 bits)
// Block Offset: 0100 (4 bits)


// Cache parameters
const int CACHE_SIZE = 1024;   // number of blocks
const int OFFSET_BITS = 4;
const int INDEX_BITS = 10;
const int TAG_BITS = 18;

enum State {
    IDLE,
    COMPARE_TAG,
    WRITE_BACK,
    ALLOCATE,
};

enum Request {
    READ,
    WRITE,
};

class CacheBlock {
public:
    bool valid;
    uint32_t tag;

    CacheBlock() : valid(false), tag(0) {}
};

class Component {
public:
    Request req;
    bool valid;
    uint32_t address;
    uint32_t writeData;
    uint32_t readData;
    bool ready;

    Component() : req(READ), valid(false), address(0), writeData(0), readData(0), ready(false) {}
};

class CPU : public Component {
public:
    CPU() : Component() {}

    void issueRequest(Request r, uint32_t addr) {
        req = r;
        address = addr;
        valid = true;
        ready = false;
    }
};

class Cache : public Component {
public:
    vector<CacheBlock> blocks;

    Cache() : Component(), blocks(CACHE_SIZE) {}

    uint32_t getIndex(uint32_t addr) {
        return (addr >> OFFSET_BITS) & ((1 << INDEX_BITS) - 1);
    }

    uint32_t getTag(uint32_t addr) {
        return addr >> (OFFSET_BITS + INDEX_BITS);
    }
};

class Memory : public Component {
public:
    Memory() : Component() {}
};

int main()
{
    State state = IDLE;

    CPU cpu;
    Cache cache;
    Memory memory;

    queue<pair<Request, uint32_t>> requests;

    // Example requests
    requests.push({READ, 0x1234});
    requests.push({WRITE, 0x5678});
    requests.push({READ, 0x1234});
    requests.push({WRITE, 0x9ABC});

    while (true)
    {
        switch (state)
        {
            case IDLE:
            {
                if (!requests.empty()) {
                    auto [req, addr] = requests.front();
                    requests.pop();

                    cpu.issueRequest(req, addr);

                    cout << "\n[IDLE] New Request -> "
                         << (req == READ ? "READ" : "WRITE")
                         << " Address: 0x" << hex << addr << dec << endl;

                    state = COMPARE_TAG;
                }
                else {
                    cout << "\nNo more requests. Exiting...\n";
                    return 0;
                }
                break;
            }

            case COMPARE_TAG:
            {
                uint32_t index = cache.getIndex(cpu.address);
                uint32_t tag = cache.getTag(cpu.address);

                CacheBlock &block = cache.blocks[index];

                cout << "[COMPARE_TAG]\n";
                cout << "Index: " << index << " Tag: " << tag << endl;

                if (block.valid && block.tag == tag) {
                    cout << "Cache HIT\n";
                    cpu.ready = true;
                    cpu.valid = false;
                    state = IDLE;
                } else {
                    cout << "Cache MISS\n";
                    // For now, just go to WRITE_BACK (we'll refine later)
                    state = WRITE_BACK;
                }

                break;
            }

            case WRITE_BACK:
            {
                cout << "[WRITE_BACK] (not implemented yet)\n";
                state = ALLOCATE;
                break;
            }

            case ALLOCATE:
            {
                cout << "[ALLOCATE] (not implemented yet)\n";

                // Simple allocation (just to keep flow correct)
                uint32_t index = cache.getIndex(cpu.address);
                uint32_t tag = cache.getTag(cpu.address);

                cache.blocks[index].valid = true;
                cache.blocks[index].tag = tag;

                cpu.ready = true;
                cpu.valid = false;

                state = IDLE;
                break;
            }
        }
    }
}