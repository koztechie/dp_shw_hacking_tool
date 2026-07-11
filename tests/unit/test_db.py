import pytest

from unittest.mock import patch, MagicMock
from src.db import get_connection, init_db

class TestDatabaseOperations:
    """Тести для операцій з базою даних."""

    @patch("src.db.duckdb.connect")
    def test_get_connection_success(self, mock_connect):
        """З'єднання успішно встановлюється з першої спроби."""
        mock_con = MagicMock()
        mock_connect.return_value = mock_con
        
        con = get_connection()
        assert con == mock_con
        mock_connect.assert_called_once()

    @patch("src.db.time.sleep")
    @patch("src.db.duckdb.connect")
    def test_get_connection_retry_success(self, mock_connect, mock_sleep):
        """Антикрихкість: З'єднання успішно встановлюється після кількох невдалих спроб."""
        mock_con = MagicMock()
        
        # Перші дві спроби падають, третя успішна
        mock_connect.side_effect = [
            Exception("Database is locked"),
            Exception("Database is locked"),
            mock_con
        ]
        
        con = get_connection(retries=5, delay=1.0)
        
        assert con == mock_con
        assert mock_connect.call_count == 3
        assert mock_sleep.call_count == 2
        # Перевірка експоненційного збільшення затримки (1.0, потім 1.5)
        mock_sleep.assert_any_call(1.0)
        mock_sleep.assert_any_call(1.5)

    @patch("src.db.time.sleep")
    @patch("src.db.duckdb.connect")
    def test_get_connection_exhausts_retries(self, mock_connect, mock_sleep):
        """Антикрихкість: Якщо всі спроби вичерпано, прокидається виняток."""
        mock_connect.side_effect = Exception("Fatal lock")
        
        with pytest.raises(Exception, match="Fatal lock"):
            get_connection(retries=3, delay=1.0)
            
        assert mock_connect.call_count == 3
        assert mock_sleep.call_count == 2

    @patch("src.utils.backup_database")
    def test_init_db(self, mock_backup, test_data_dir):
        """init_db успішно створює всі необхідні таблиці та індекси."""
        test_db_path = str(test_data_dir / "init_test.duckdb")
        
        with patch("src.db.DB_PATH", test_db_path):
            init_db()
            
            # Перевіряємо, що резервне копіювання було викликано
            mock_backup.assert_called_once_with(test_db_path)
            
            # Підключаємось до тестової БД, щоб перевірити наявність таблиць
            import duckdb
            con = duckdb.connect(test_db_path)
            
            # Отримуємо список всіх таблиць
            tables = [row[0] for row in con.execute("SHOW TABLES").fetchall()]
            
            expected_tables = [
                "hackathons",
                "projects",
                "features",
                "predictions",
                "feedback",
                "experiments",
                "audit_log"
            ]
            
            for table in expected_tables:
                assert table in tables
                
            con.close()
