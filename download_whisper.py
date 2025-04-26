import argparse
from faster_whisper import WhisperModel
import os
import shutil # 用於檔案複製
import glob   # 用於尋找 snapshot 目錄

VALID_MODELS = {
    "tiny", "tiny.en", "base", "base.en", "small", "small.en",
    "medium", "medium.en", "large-v1", "large-v2", "large-v3",
    "distil-small.en", "distil-medium.en", "distil-large-v2" # 加入更多有效模型
}

# Hugging Face 上的 Repo Owner (通常是 Systran 或 openai)
# faster-whisper 預設使用 Systran 的版本
MODEL_OWNER_MAP = {
    "tiny": "Systran", "tiny.en": "Systran",
    "base": "Systran", "base.en": "Systran",
    "small": "Systran", "small.en": "Systran",
    "medium": "Systran", "medium.en": "Systran",
    "large-v1": "Systran", "large-v2": "Systran", "large-v3": "Systran",
    "distil-small.en": "Systran", "distil-medium.en": "Systran",
    "distil-large-v2": "Systran",
    # 如果未來 faster-whisper 改用 openai 或其他來源，可以在這裡更新
    # "large-v3": "openai" # 範例
}

def main():
    parser = argparse.ArgumentParser(
        description="批次下載Whisper STT模型並整理成平坦目錄結構",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "models",
        type=str,
        help=f"用逗號分隔要下載的模型列表，有效選項包含： {', '.join(sorted(VALID_MODELS))}"
    )
    parser.add_argument(
        "--download_root",
        default="models",
        help="指定保存最終模型文件和下載快取的根目錄"
    )
    parser.add_argument(
        "--force_cpu",
        action="store_true",
        help="強制使用CPU進行下載驗證(預設自動選擇裝置)"
    )
    parser.add_argument(
        "--cleanup_cache",
        action="store_true",
        help="在複製完成後刪除 Hugging Face 的快取目錄"
    )

    args = parser.parse_args()
    model_names = [m.strip().lower() for m in args.models.split(",")]

    # 確認模型名稱
    invalid = [m for m in model_names if m not in VALID_MODELS]
    if invalid:
        print(f"錯誤: 無效的模型名稱 {', '.join(invalid)}")
        print(f"有效選項：{', '.join(sorted(VALID_MODELS))}")
        return 1

    device = "cpu" if args.force_cpu else "auto"

    # 確保根目錄存在
    os.makedirs(args.download_root, exist_ok=True)
    # Hugging Face 快取會存在 download_root 下，符合其預期行為
    cache_dir = args.download_root

    for model_name in model_names:
        model = None # 初始化 model 變數
        try:
            print(f"\n--- 處理模型：{model_name} ---")

            # 1. 使用 faster-whisper 下載模型到 Hugging Face 快取
            print(f"步驟 1: 開始下載 '{model_name}' 到快取目錄 {cache_dir}...")
            model = WhisperModel(
                model_name,
                device=device,
                compute_type="int8", # 使用 int8 以減少驗證時的記憶體使用，下載的文件是一樣的
                download_root=cache_dir
            )
            print(f"模型 '{model_name}' 下載並初步驗證完成。")

            # 2. 找到 Hugging Face 快取中的 snapshot 目錄
            print("步驟 2: 尋找快取中的模型文件...")
            owner = MODEL_OWNER_MAP.get(model_name, "Systran") # 預設用 Systran
            # 注意：HuggingFace 上的模型名稱可能包含 '.'，但在快取目錄中通常會被替換
            # 但 faster-whisper 可能內部有處理，我們先嘗試直接用 model_name
            # 快取目錄的命名規則通常是 models--{owner}--{repo_name}
            # faster-whisper 內部使用的 repo name 通常是 faster-whisper-{model_name}
            hf_repo_name = f"faster-whisper-{model_name}"
            cache_model_dir_pattern = os.path.join(cache_dir, f"models--{owner}--{hf_repo_name}")

            # 檢查快取目錄是否存在
            matching_dirs = glob.glob(cache_model_dir_pattern)
            if not matching_dirs:
                 # 有些模型名稱可能不同，例如 distil 系列
                 hf_repo_name_alt = f"distil-whisper-{model_name.replace('distil-','')}"
                 cache_model_dir_pattern_alt = os.path.join(cache_dir, f"models--{owner}--{hf_repo_name_alt}")
                 matching_dirs = glob.glob(cache_model_dir_pattern_alt)
                 if not matching_dirs:
                    print(f"錯誤: 找不到模型 '{model_name}' 的快取目錄，預期路徑模式: {cache_model_dir_pattern} 或 {cache_model_dir_pattern_alt}")
                    continue # 處理下一個模型
                 else:
                    cache_model_dir = matching_dirs[0]
                    hf_repo_name = hf_repo_name_alt # 更新 repo name 以便後續使用

            else:
                 cache_model_dir = matching_dirs[0] # 通常只會有一個匹配

            snapshot_dir_pattern = os.path.join(cache_model_dir, "snapshots", "*")
            snapshot_dirs = glob.glob(snapshot_dir_pattern)

            if not snapshot_dirs:
                print(f"錯誤: 在 {cache_model_dir} 中找不到 snapshot 目錄。")
                continue

            # 通常只有一個 snapshot，但以防萬一，取最新的 (或第一個)
            snapshot_path = snapshot_dirs[0]
            if len(snapshot_dirs) > 1:
                print(f"警告: 找到多個 snapshots，將使用第一個: {snapshot_path}")

            print(f"找到 Snapshot 目錄: {snapshot_path}")

            # 3. 設定目標目錄並複製文件
            # 目標目錄名稱直接使用 hf_repo_name，例如 faster-whisper-medium
            target_dir = os.path.join(args.download_root, hf_repo_name)
            print(f"步驟 3: 複製文件到目標目錄: {target_dir}")

            os.makedirs(target_dir, exist_ok=True)

            copied_files = []
            failed_files = []

            # 遍歷 snapshot 目錄中的所有項目
            for item_name in os.listdir(snapshot_path):
                source_item_path = os.path.join(snapshot_path, item_name)
                target_item_path = os.path.join(target_dir, item_name)

                try:
                    if os.path.isfile(source_item_path) or os.path.islink(source_item_path):
                         # 重要：使用 shutil.copy2 複製實際文件（如果 source 是連結，會複製連結指向的文件）
                         # 並且會保留文件的元數據（如修改時間）
                         shutil.copy2(source_item_path, target_item_path)
                         # print(f"  複製: {item_name}")
                         copied_files.append(item_name)
                    # else: # 忽略目錄或其他非文件類型
                    #    print(f"  忽略: {item_name} (非文件或連結)")
                except Exception as copy_e:
                    print(f"  複製文件 {item_name} 時出錯: {copy_e}")
                    failed_files.append(item_name)

            if not failed_files:
                print(f"成功將 {len(copied_files)} 個文件複製到 {target_dir}")
                print(f"模型 '{model_name}' 的平坦結構已建立於: {target_dir}")

                # 4. (可選) 清理 Hugging Face 快取
                if args.cleanup_cache:
                    print(f"步驟 4: 清理快取目錄 {cache_model_dir}...")
                    try:
                        shutil.rmtree(cache_model_dir)
                        print(f"成功刪除快取目錄: {cache_model_dir}")
                    except Exception as clean_e:
                        print(f"清理快取目錄 {cache_model_dir} 時出錯: {clean_e}")
            else:
                print(f"錯誤: 部分文件複製失敗: {', '.join(failed_files)}")
                print(f"目標目錄 {target_dir} 可能不完整。")


        except Exception as e:
            print(f"處理模型 '{model_name}' 時發生未預期的錯誤: {str(e)}")
        finally:
             # 確保釋放模型資源，即使過程中出錯
             if model is not None:
                # print("釋放 WhisperModel 資源...")
                del model # 釋放 GPU/CPU 資源

if __name__ == "__main__":
    main()