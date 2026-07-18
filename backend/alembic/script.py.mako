# ==============================================================================
# Alembic 迁移脚本模板 (Mako)
# ==============================================================================
# 使用 alembic revision 命令生成新迁移时, 会基于此模板创建文件。
# 自动填充项:
#   ${revision}      - 新版本号 (默认为 SHA 哈希)
#   ${down_revision} - 上一版本号
#   ${branch_labels} - 分支标签
#   ${depends_on}    - 依赖项
#   ${upgraded_at}   - 升级时间戳
#   ${downgraded_at} - 降级时间戳
# ==============================================================================

"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
