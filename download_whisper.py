import argparse
from faster_whisper import WhisperModel
import os
import shutil # 用於檔案複製
import glob   # 用於尋找 snapshot 目錄

# --- 修改開始: 更新 VALID_MODELS ---
VALID_MODELS = {
    "tiny", "tiny.en",
    "base", "base.en",
    "small", "small.en",
    "medium", "medium.en",
    "large-v1", "large-v2", "large-v3",
    "distil-small.en", "distil-medium.en", "distil-large-v2", "distil-large-v3" # 加入圖片中所有模型
}
# --- 修改結束 ---

# --- 修改開始: 更新 MODEL_OWNER_MAP ---
# Hugging Face 上的 Repo Owner (通常是 Systran 或 openai)
# faster-whisper 預設使用 Systran 的版本
# 根據圖片，這些模型都來自 Systran
MODEL_OWNER_MAP = {
    "tiny": "Systran", "tiny.en": "Systran",
    "base": "Systran", "base.en": "Systran",
    "small": "Systran", "small.en": "Systran",
    "medium": "Systran", "medium.en": "Systran",
    "large-v1": "Systran", "large-v2": "Systran", "large-v3": "Systran",
    "distil-small.en": "Systran", "distil-medium.en": "Systran",
    "distil-large-v2": "Systran", "distil-large-v3": "Systran", # 加入 distil-large-v3
    # 如果未來 faster-whisper 改用 openai 或其他來源，可以在這裡更新
    # "large-v3": "openai" # 範例
}
# --- 修改結束 ---


def main():
    parser = argparse.ArgumentParser(
        description="批次下載Whisper STT模型並整理成平坦目錄結構",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "models",
        type=str,
        # 使用更新後的 VALID_MODELS 產生說明文字
        help=f"用逗號分隔要下載的模型列表，有效選項包含： {', '.join(sorted(list(VALID_MODELS)))}"
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
        # 使用更新後的 VALID_MODELS 產生有效選項列表
        print(f"有效選項：{', '.join(sorted(list(VALID_MODELS)))}")
        return 1

    device = "cpu" if args.force_cpu else "auto"

    # 確保根目錄存在
    os.makedirs(args.download_root, exist_ok=True)
    # Hugging Face 快取會存在 download_root 下，符合其預期行為
    cache_dir = args.download_root

    for model_name in model_names:
        model = None # 初始化 model 變數
        cache_model_dir = None # 初始化快取目錄路徑
        hf_repo_name = None # 初始化找到的 repo name
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
            # 使用更新後的 MODEL_OWNER_MAP
            owner = MODEL_OWNER_MAP.get(model_name, "Systran") # 預設用 Systran

            # 構建可能的 Hugging Face 儲存庫名稱列表
            possible_repo_names = []
            # 1. 標準 faster-whisper 格式
            possible_repo_names.append(f"faster-whisper-{model_name}")
            # 2. 針對 distil 系列的特殊格式
            if model_name.startswith("distil-"):
                distil_base_name = model_name.replace("distil-", "")
                possible_repo_names.append(f"faster-distil-whisper-{distil_base_name}")
            # 可以根據需要加入更多可能的格式

            matching_dirs = []
            found_repo_name = None
            print(f"嘗試尋找以下可能的快取目錄模式 (在 {cache_dir} 下):")
            for repo_candidate in possible_repo_names:
                pattern = os.path.join(cache_dir, f"models--{owner}--{repo_candidate}")
                print(f"  - 檢查模式: {pattern}")
                current_matches = glob.glob(pattern)
                if current_matches:
                    matching_dirs.extend(current_matches)
                    found_repo_name = repo_candidate # 儲存成功匹配的 repo name
                    print(f"    找到匹配: {current_matches[0]}")
                    break # 找到一個就停止，假設這是正確的

            if not matching_dirs:
                print(f"錯誤: 找不到模型 '{model_name}' 的快取目錄。")
                print("請檢查 download_root 目錄下的 'models--*' 子目錄，確認實際的快取目錄名稱。")
                continue # 處理下一個模型

            # 通常只會有一個匹配，取第一個
            cache_model_dir = matching_dirs[0]
            hf_repo_name = found_repo_name # 使用實際找到的 repo name
            print(f"找到快取目錄: {cache_model_dir} (使用 repo name: {hf_repo_name})")

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
            # 目標目錄名稱使用實際找到的 hf_repo_name
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
                         shutil.copy2(source_item_path, target_item_path)
                         copied_files.append(item_name)
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
            import traceback
            print(f"處理模型 '{model_name}' 時發生未預期的錯誤: {str(e)}")
            # traceback.print_exc()
        finally:
             if model is not None:
                try:
                    del model
                except NameError:
                    pass
             cache_model_dir = None
             hf_repo_name = None

if __name__ == "__main__":
    main()