PR created: https://github.com/wfurlow3/CS230-healthcare/pull/19

The PR adds comprehensive random seed management for reproducible training:
- Created `set_seed()` utility function in `src/utils.py` that sets seeds for Python random, NumPy, PyTorch CPU/CUDA, cuDNN deterministic mode, and PYTHONHASHSEED
- Updated `src/train_mlm.py` to use `set_seed()` instead of inline seed setting
- Modified `src/dataset.py` to use a seeded `torch.Generator` for reproducible DataLoader shuffling
- Updated LOS baseline scripts to use `set_seed()` (previously missing Python random and CUDA seeds)
- Added documentation to the `SEED` constant in `src/config.py`

No CI checks are configured for this repo. Note that `cudnn.deterministic=True` may reduce GPU training performance by 10-20%.