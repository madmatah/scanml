package fr.scanmylib.db

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase

@Database(
    entities = [DocumentEntity::class, PendingPageEntity::class, ServerPageEntity::class],
    version = 1,
)
abstract class ScanMyLibDatabase : RoomDatabase() {
    abstract fun documentDao(): DocumentDao

    abstract fun pendingPageDao(): PendingPageDao

    abstract fun serverPageDao(): ServerPageDao

    companion object {
        fun create(context: Context): ScanMyLibDatabase =
            Room.databaseBuilder(context, ScanMyLibDatabase::class.java, "scanmylib.db").build()
    }
}
