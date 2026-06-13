import asyncio
import aiohttp
import time

# ĐIỀN LINK CLOUDFLARE HIỆN TẠI VÀO ĐÂY
URL = "https://technique-argument-inspection-frame.trycloudflare.com/api/tts"

PAYLOAD = {
    "text": "Xin chào. Đây là bài kiểm tra độ chịu tải trên Mac Mini.",
    "voice": ""
}

async def send_request(session, req_id):
    start_time = time.time()
    try:
        print(f"[{req_id}] Bắt đầu gửi...")
        async with session.post(URL, json=PAYLOAD, timeout=aiohttp.ClientTimeout(total=600)) as response:
            status = response.status
            elapsed = time.time() - start_time
            if status == 200:
                print(f"[{req_id}] ✅ Xong! Mất {elapsed:.1f}s")
            else:
                print(f"[{req_id}] ❌ Lỗi {status} sau {elapsed:.1f}s")
    except Exception as e:
        print(f"[{req_id}] ⚠️ Đứt kết nối: {e}")

async def main(concurrent_users=5):
    print(f"🚀 BẮT ĐẦU STRESS TEST VỚI {concurrent_users} USER CÙNG LÚC")
    print(f"Target: {URL}")
    print("-" * 50)
    
    start_all = time.time()
    async with aiohttp.ClientSession() as session:
        tasks = [send_request(session, i) for i in range(1, concurrent_users + 1)]
        await asyncio.gather(*tasks)
        
    print("-" * 50)
    print(f"🏁 TỔNG THỜI GIAN HOÀN THÀNH: {time.time() - start_all:.1f}s")

if __name__ == "__main__":
    # Thay đổi số lượng user ảo ở đây
    asyncio.run(main(concurrent_users=100))
